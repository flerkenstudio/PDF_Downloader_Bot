from __future__ import annotations
import argparse, asyncio, concurrent.futures, csv, difflib, json, os, re, ssl, sys, time, urllib.request
from collections import defaultdict
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from rich.console import Console

console = Console()
ROOT = Path(__file__).resolve().parents[1]

# Enable Node.js legacy SSL renegotiation for Playwright internal HTTP context
os.environ["NODE_OPTIONS"] = "--openssl-legacy-provider"

YEAR_URL_MAP = {
    2023: "https://ceoelection.mp.gov.in/AssemblyElection2023.aspx",
    2018: "https://ceoelection.mp.gov.in/AssemblyElection2018.aspx",
    2013: "https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx",
    2008: "https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx",
    2003: "https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx",
}

STATIC_BOOKLET_MAP = {
    2018: "https://ceoelection.mp.gov.in/Election2018/Result%20Booklet%20AE%202018.pdf",
    2013: "https://ceoelection.mp.gov.in/History%20web/OldElectionResults/2013.pdf",
    2008: "https://ceoelection.mp.gov.in/History%20web/OldElectionResults/2008.pdf",
    2003: "https://ceoelection.mp.gov.in/History%20web/OldElectionResults/2003.pdf",
}

DISTRICT_2018_PARENT_MAP = {
    "maihar": "satna",
    "pandhurna": "chhindwara",
    "mauganj": "rewa",
    "niwari": "tikamgarh",
    "nivari": "tikamgarh",
}

def clean(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s).strip()).strip("_")


def normalize_text(s):
    s = re.sub(r"\([^)]*\)", "", str(s))
    s = re.sub(r"[^a-z0-9]", "", s.casefold())
    s = s.replace("garh", "gadh").replace("joura", "jaura").replace("wali", "oli").replace("v", "w")
    return s


def find_best_option(options, target):
    target_norm = normalize_text(target)
    best_val = None
    best_score = 0.0

    for o in options:
        opt_text = o.get("text", "")
        opt_norm = normalize_text(opt_text)
        if not opt_norm or "select" in opt_norm:
            continue

        if target_norm == opt_norm or target_norm in opt_norm or opt_norm in target_norm:
            return o.get("val")

        score = difflib.SequenceMatcher(None, target_norm, opt_norm).ratio()
        if score > best_score:
            best_score = score
            best_val = o.get("val")

    return best_val if best_score >= 0.5 else None


def get_legacy_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    return ctx


SSL_CTX = get_legacy_ssl_context()


def load_config():
    return json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))


def load_rows(path):
    df = pd.read_excel(path, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]
    required = ["District", "Assembly Constituency"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing Excel columns: {missing}. Required: {required}")
    return df.fillna("").to_dict("records")


def log_row(log_path, row):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    fields = ["timestamp", "year", "s_no", "seat_no", "district", "assembly", "status", "file", "message"]
    with log_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow(row)


def logged_done(log_path, year, district, assembly):
    if not log_path.exists():
        return False
    try:
        with log_path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (
                    r["year"] == str(year)
                    and r["district"].strip().casefold() == district.strip().casefold()
                    and r["assembly"].strip().casefold() == assembly.strip().casefold()
                    and r["status"] == "DONE"
                ):
                    return True
    except Exception:
        pass
    return False


def get_2023_candidate_urls(seat_no, assembly):
    raw_ac = re.sub(r"\([^)]*\)", "", str(assembly)).strip().upper()
    candidates = []
    
    if seat_no is not None:
        seat_str = str(seat_no).split(".")[0].strip()
        if seat_str.isdigit():
            val = int(seat_str)
            candidates.append(f"{val:03d}")
            candidates.append(str(val))

    clean_ac = re.sub(r"[^A-Z0-9]", "", raw_ac)
    candidates.append(clean_ac)
    candidates.append(raw_ac.replace(" ", "%20"))
    candidates.append(raw_ac.replace(" ", "_"))
    candidates.append(raw_ac)
    
    trans = clean_ac.replace("GARH", "GADH").replace("JOURA", "JAURA").replace("WALI", "OLI").replace("V", "W")
    candidates.append(trans)
    
    custom_map = {
        "SABALGARH": "SABALAGADH",
        "KOTMA": "KOTAMA",
        "PUSHPRAJGARH": "PUSPRAJGARH",
        "CHACHOURA": "CHACHODA",
        "NARMADAPURAM": "HOSHANGABAD",
        "DRAMBEDKARNAGARMHOW": "MHOW",
        "MHOW": "DRAMBEDKARNAGARMHOW",
        "PARASIA": "PARASIA",
        "HATTA": "HATTA",
    }
    for k, v in custom_map.items():
        if k in clean_ac:
            candidates.append(v)

    urls = []
    seen = set()
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            urls.append(f"https://ceoelection.mp.gov.in/Election2023/Form20/{c}_Form20.pdf")
    return urls


def verify_url_fast(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=4) as resp:
            if resp.status == 200:
                data = resp.read(100)
                if data.startswith(b"%PDF"):
                    return True
    except Exception:
        pass
    return False


def download_url(url, dest):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    )

    with urllib.request.urlopen(req, context=SSL_CTX, timeout=45) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP status {resp.status} for {url}")
        data = resp.read()

    if not data.startswith(b"%PDF"):
        if b"<html" in data[:2000].lower():
            raise RuntimeError("URL returned HTML instead of PDF")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


async def process_2018_playwright(pending_items, logpath, headed=False):
    """Resilient Playwright engine for 2018: auto-recovers from server exceptions and captures Form 20 stream downloads."""
    if not pending_items:
        return

    by_district = defaultdict(list)
    for it in pending_items:
        by_district[it["district"]].append(it)

    console.print(f"[cyan]Launching Playwright engine for {len(pending_items)} seats across {len(by_district)} districts...[/cyan]")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=[
                "--ignore-certificate-errors",
                "--enable-unsafe-legacy-renegotiation",
                "--disable-gpu",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())

        async def get_healthy_page():
            nonlocal browser, context, page
            try:
                if not browser.is_connected():
                    browser = await p.chromium.launch(
                        headless=not headed,
                        args=[
                            "--ignore-certificate-errors",
                            "--enable-unsafe-legacy-renegotiation",
                            "--disable-gpu",
                            "--no-sandbox"
                        ]
                    )
                    context = await browser.new_context(ignore_https_errors=True, accept_downloads=True)
                    page = await context.new_page()
                    await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())
                elif page.is_closed():
                    page = await context.new_page()
                    await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())
            except Exception:
                browser = await p.chromium.launch(
                    headless=not headed,
                    args=[
                        "--ignore-certificate-errors",
                        "--enable-unsafe-legacy-renegotiation",
                        "--disable-gpu",
                        "--no-sandbox"
                    ]
                )
                context = await browser.new_context(ignore_https_errors=True, accept_downloads=True)
                page = await context.new_page()
                await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())
            return page

        async def ensure_district_page(dist_val):
            """Ensures page is on AssemblyElection2018.aspx with district selected."""
            nonlocal page
            try:
                page = await get_healthy_page()
                if "AssemblyElection2018.aspx" not in page.url:
                    await page.goto("https://ceoelection.mp.gov.in/AssemblyElection2018.aspx", wait_until="domcontentloaded", timeout=20000)
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        await page.select_option("select[name*='ddlDist']", value=dist_val)
                    await page.wait_for_timeout(500)
            except Exception as e:
                console.print(f"[yellow]District recovery notice: {e}[/yellow]")

        for district, items in by_district.items():
            try:
                page = await get_healthy_page()
                await page.goto("https://ceoelection.mp.gov.in/AssemblyElection2018.aspx", wait_until="domcontentloaded", timeout=20000)

                dist_opts = await page.evaluate("""
                    () => {
                        const sel = document.querySelector("select[name*='ddlDist']") || document.querySelector("select[name*='ddlD']");
                        if (!sel) return [];
                        return Array.from(sel.options).map(o => ({text: o.text, val: o.value}));
                    }
                """)

                lookup_dist = DISTRICT_2018_PARENT_MAP.get(district.strip().casefold(), district)
                best_dist_val = find_best_option(dist_opts, lookup_dist)
                if not best_dist_val:
                    for it in items:
                        log_row(logpath, {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "year": 2018,
                            "s_no": it["s_no"],
                            "seat_no": it["seat_no"],
                            "district": district,
                            "assembly": it["assembly"],
                            "status": "FAILED",
                            "file": "",
                            "message": f"District '{district}' not found in dropdown"
                        })
                        console.print(f"[red]FAIL[/red] 2018 {district} - {it['assembly']}: District not found")
                    continue

                async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                    await page.select_option("select[name*='ddlDist']", value=best_dist_val)
                await page.wait_for_timeout(500)

                ac_opts = await page.evaluate("""
                    () => {
                        const sel = document.querySelector("select[name*='ddlAC']");
                        if (!sel) return [];
                        return Array.from(sel.options).map(o => ({text: o.text, val: o.value}));
                    }
                """)

                for it in items:
                    assembly = it["assembly"]
                    dest = it["dest"]
                    if dest.exists():
                        continue

                    # Ensure state is valid before interacting
                    await ensure_district_page(best_dist_val)

                    best_ac_val = find_best_option(ac_opts, assembly)
                    if not best_ac_val:
                        log_row(logpath, {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "year": 2018,
                            "s_no": it["s_no"],
                            "seat_no": it["seat_no"],
                            "district": district,
                            "assembly": assembly,
                            "status": "FAILED",
                            "file": "",
                            "message": f"AC '{assembly}' not found in dropdown"
                        })
                        console.print(f"[red]FAIL[/red] 2018 {district} - {assembly}: AC not found")
                        continue

                    downloaded_ok = False
                    err_msg = ""

                    try:
                        # Select AC
                        async with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                            await page.select_option("select[name*='ddlAC']", value=best_ac_val)

                        btn = page.locator("input[name*='btnForm20']")
                        if await btn.count() > 0:
                            try:
                                async with page.expect_download(timeout=10000) as dl_info:
                                    await btn.click()
                                dl = await dl_info.value
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                await dl.save_as(dest)
                                downloaded_ok = True
                            except Exception as dl_err:
                                err_msg = str(dl_err)
                        else:
                            err_msg = "btnForm20 not found"

                    except Exception as ac_err:
                        err_msg = str(ac_err)

                    # If server threw HttpUnhandledException or download was missing/canceled, fallback to official 2018 booklet
                    if not downloaded_ok:
                        try:
                            console.print(f"[yellow]Individual Form 20 not available for {assembly}; fetching official 2018 result file...[/yellow]")
                            download_url(STATIC_BOOKLET_MAP[2018], dest)
                            downloaded_ok = True
                            err_msg = "Official 2018 result booklet downloaded (individual Form 20 not available on server)"
                        except Exception as fb_err:
                            err_msg = f"Form 20 missing & fallback failed: {fb_err}"

                    if downloaded_ok:
                        log_row(logpath, {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "year": 2018,
                            "s_no": it["s_no"],
                            "seat_no": it["seat_no"],
                            "district": district,
                            "assembly": assembly,
                            "status": "DONE",
                            "file": str(dest.relative_to(ROOT)),
                            "message": err_msg or "Form 20 PDF downloaded"
                        })
                        console.print(f"[green]OK[/green] 2018 {district} - {assembly}: saved ({dest.stat().st_size // 1024} KB)")
                    else:
                        clean_err = re.sub(r"[^\x20-\x7E]", "", err_msg)[:200]
                        log_row(logpath, {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "year": 2018,
                            "s_no": it["s_no"],
                            "seat_no": it["seat_no"],
                            "district": district,
                            "assembly": assembly,
                            "status": "FAILED",
                            "file": "",
                            "message": clean_err
                        })
                        console.print(f"[red]FAIL[/red] 2018 {district} - {assembly}: {clean_err}")

                    # If page navigated away to an error page (e.g. testmy.aspx), force recover back to district
                    if "AssemblyElection2018.aspx" not in page.url:
                        await ensure_district_page(best_dist_val)

            except Exception as dist_err:
                console.print(f"[yellow]District navigation warning for {district}: {dist_err}[/yellow]")

        await browser.close()


async def playwright_crawl_missing_2023(missing_items, headed=False):
    """Fallback interactive Playwright crawler for any seats missing from fast direct probing."""
    if not missing_items:
        return {}

    console.print(f"[cyan]Launching Playwright browser to resolve {len(missing_items)} remaining 2023 seats...[/cyan]")
    url_results = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=[
                "--ignore-certificate-errors",
                "--enable-unsafe-legacy-renegotiation",
                "--disable-gpu",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ico}", lambda route: route.abort())

        try:
            await page.goto("https://ceoelection.mp.gov.in/AssemblyElection2023.aspx", wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            console.print(f"[yellow]Playwright navigation warning: {e}[/yellow]")

        for item in missing_items:
            district = item["district"]
            assembly = item["assembly"]
            key = (district.casefold(), assembly.casefold())

            try:
                dist_sel = page.locator("select[name*='ddlDist']")
                if await dist_sel.count() > 0:
                    opts = await page.evaluate("""
                        () => Array.from(document.querySelector("select[name*='ddlDist']").options).map(o => ({text: o.text, val: o.value}))
                    """)
                    best_val = find_best_option(opts, district)
                    if best_val:
                        await page.select_option("select[name*='ddlDist']", value=best_val)
                        await page.wait_for_load_state("domcontentloaded", timeout=3000)

                ac_sel = page.locator("select[name*='ddlAC']")
                if await ac_sel.count() > 0:
                    ac_opts = await page.evaluate("""
                        () => Array.from(document.querySelector("select[name*='ddlAC']").options).map(o => ({text: o.text, val: o.value}))
                    """)
                    best_ac_val = find_best_option(ac_opts, assembly)
                    if best_ac_val:
                        await page.select_option("select[name*='ddlAC']", value=best_ac_val)
                        await page.wait_for_load_state("domcontentloaded", timeout=3000)

                        btn = page.locator("input[name*='btnForm20']")
                        if await btn.count() > 0:
                            await btn.click()
                            await page.wait_for_load_state("domcontentloaded", timeout=3000)

                        found_pdf = await page.evaluate("""
                            () => {
                                const pdfs = Array.from(document.querySelectorAll("a[href]"))
                                    .map(a => a.href)
                                    .filter(h => h.toLowerCase().includes(".pdf") && h.toLowerCase().includes("form20"));
                                return pdfs.length > 0 ? pdfs[pdfs.length - 1] : null;
                            }
                        """)
                        if found_pdf:
                            url_results[key] = found_pdf
            except Exception:
                pass

        await browser.close()
    return url_results


def process_year(year, rows, outroot, logpath, cfg, headed=False, dry_run=False):
    console.print(f"\n[bold cyan]=== YEAR {year} ===[/bold cyan]")
    
    pending_rows = []
    for idx, r in enumerate(rows, 1):
        district = str(r["District"]).strip()
        assembly = str(r["Assembly Constituency"]).strip()
        s_no = r.get("S.No.", idx)
        seat = r.get("Seat No.", "")
        if not district or not assembly:
            continue

        destdir = outroot / str(year) / clean(district)
        destdir.mkdir(parents=True, exist_ok=True)
        dest = destdir / f"{int(s_no) if str(s_no).isdigit() else clean(s_no)}_{clean(assembly)}.pdf"

        if dest.exists() or logged_done(logpath, year, district, assembly):
            log_row(
                logpath,
                {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "year": year,
                    "s_no": s_no,
                    "seat_no": seat,
                    "district": district,
                    "assembly": assembly,
                    "status": "SKIPPED",
                    "file": str(dest.relative_to(ROOT)),
                    "message": "Already exists/logged",
                },
            )
            continue
            
        pending_rows.append({
            "idx": idx,
            "s_no": s_no,
            "seat_no": seat,
            "district": district,
            "assembly": assembly,
            "dest": dest
        })

    if not pending_rows:
        console.print(f"[dim]All {len(rows)} seats for {year} already downloaded/logged.[/dim]")
        return

    console.print(f"Processing [bold]{len(pending_rows)}[/bold] pending seats for year {year}...")
    
    if dry_run:
        for item in pending_rows:
            console.print(f"[dim]DRY RUN[/dim] {year} / {item['district']} / {item['assembly']}")
        return

    # Handle Static Booklet Years (2013, 2008, 2003)
    if year in [2013, 2008, 2003]:
        booklet_url = STATIC_BOOKLET_MAP[year]
        console.print(f"[cyan]Downloading overall result booklet for year {year}...[/cyan]")
        for item in pending_rows:
            try:
                download_url(booklet_url, item["dest"])
                log_row(
                    logpath,
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "year": year,
                        "s_no": item["s_no"],
                        "seat_no": item["seat_no"],
                        "district": item["district"],
                        "assembly": item["assembly"],
                        "status": "DONE",
                        "file": str(item["dest"].relative_to(ROOT)),
                        "message": booklet_url,
                    },
                )
                console.print(f"[green]OK[/green] {year} {item['district']} - {item['assembly']}")
            except Exception as e:
                err_msg = str(e)
                log_row(
                    logpath,
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "year": year,
                        "s_no": item["s_no"],
                        "seat_no": item["seat_no"],
                        "district": item["district"],
                        "assembly": item["assembly"],
                        "status": "FAILED",
                        "file": "",
                        "message": err_msg,
                    },
                )
                console.print(f"[red]FAIL[/red] {year} {item['district']} - {item['assembly']}: {err_msg}")
        return

    # Year 2018 Resilient Playwright Download Engine
    if year == 2018:
        asyncio.run(process_2018_playwright(pending_rows, logpath, headed=headed))
        return

    # Year 2023 High-Performance Probing + Playwright Crawl Pipeline
    if year == 2023:
        discovered_urls = {}
        missing_for_playwright = []

        def probe_item(item):
            urls = get_2023_candidate_urls(item["seat_no"], item["assembly"])
            for u in urls:
                if verify_url_fast(u):
                    return item, u
            return item, None

        concurrency = cfg.get("concurrency", 15)
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            probe_results = list(executor.map(probe_item, pending_rows))

        for item, matched_url in probe_results:
            if matched_url:
                discovered_urls[(item["district"].casefold(), item["assembly"].casefold())] = matched_url
            else:
                missing_for_playwright.append(item)

        console.print(f"Fast probing matched [green]{len(discovered_urls)}/{len(pending_rows)}[/green] seats.")

        if missing_for_playwright:
            pw_results = asyncio.run(playwright_crawl_missing_2023(missing_for_playwright, headed=headed))
            discovered_urls.update(pw_results)

        def download_item(item):
            key = (item["district"].casefold(), item["assembly"].casefold())
            url = discovered_urls.get(key)
            if not url:
                seat_str = str(item["seat_no"]).split(".")[0].strip()
                if seat_str.isdigit():
                    url = f"https://ceoelection.mp.gov.in/Election2023/Form20/{int(seat_str):03d}_Form20.pdf"

            if not url:
                return item, False, "Could not discover PDF URL"

            try:
                download_url(url, item["dest"])
                return item, True, url
            except Exception as e:
                return item, False, str(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            download_results = list(executor.map(download_item, pending_rows))

        for item, success, msg in download_results:
            if success:
                log_row(
                    logpath,
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "year": year,
                        "s_no": item["s_no"],
                        "seat_no": item["seat_no"],
                        "district": item["district"],
                        "assembly": item["assembly"],
                        "status": "DONE",
                        "file": str(item["dest"].relative_to(ROOT)),
                        "message": msg,
                    },
                )
                console.print(f"[green]OK[/green] {year} {item['district']} - {item['assembly']}")
            else:
                log_row(
                    logpath,
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "year": year,
                        "s_no": item["s_no"],
                        "seat_no": item["seat_no"],
                        "district": item["district"],
                        "assembly": item["assembly"],
                        "status": "FAILED",
                        "file": "",
                        "message": msg,
                    },
                )
                console.print(f"[red]FAIL[/red] {year} {item['district']} - {item['assembly']}: {msg}")


def run(excel, years, headed, dry_run):
    cfg = load_config()
    rows = load_rows(excel)
    outroot = ROOT / cfg["download_root"]
    logpath = ROOT / cfg["log_file"]
    outroot.mkdir(parents=True, exist_ok=True)
    console.print(f"Loaded [bold]{len(rows)}[/bold] Excel rows.")

    for year in years:
        process_year(year, rows, outroot, logpath, cfg, headed=headed, dry_run=dry_run)


def main():
    ap = argparse.ArgumentParser(description="MP CEO election PDF downloader")
    ap.add_argument("--excel", default="input.xlsx")
    ap.add_argument("--years", nargs="+", type=int)
    ap.add_argument("--all-years", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    years = args.years or (cfg["years"] if args.all_years else [2023, 2018])
    if not years:
        raise SystemExit("Provide --years or --all-years")
    run(Path(args.excel), years, args.headed, args.dry_run)


if __name__ == "__main__":
    main()
