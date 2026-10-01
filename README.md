# MP CEO Election PDF Downloader Bot

Automates PDF collection from the Chief Electoral Officer, Madhya Pradesh Assembly Election portal (`ceoelection.mp.gov.in`) using an Excel file containing District and Assembly Constituency lists.

Official Portal: [https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx](https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx)

---

## Features

- **Automated ASP.NET Postback Navigation**: Interacts with dynamic WebForms cascading dropdowns (`ddlDist` / `ddlD` $\rightarrow$ `ddlAC`) and dispatches change events to trigger server-side updates.
- **Fuzzy Name & Transliteration Matching**: Uses normalization and `difflib.SequenceMatcher` to handle spelling variations between Excel and website dropdown labels (e.g. `Sabalgarh` $\leftrightarrow$ `SABALAGADH`, `Joura` $\leftrightarrow$ `JAURA`, `Sumawali` $\leftrightarrow$ `SUMAOLI`, stripping `(SC)`/`(ST)` suffixes).
- **Legacy SSL Support**: Custom HTTP transport layer using Python `urllib` with `OP_LEGACY_SERVER_CONNECT` to handle legacy government server SSL renegotiation.
- **Resumable & Logged Downloads**: Logs status (`DONE`, `FAILED`, `SKIPPED`) to `logs/download_log.csv` and skips already downloaded PDFs.
- **Cross-Platform & Headless Support**: Run in headless or visible browser modes (`--headed`).

---

## Directory Structure

```text
MP_Election_PDF_Downloader_Bot/
├── mpbot/
│   ├── config/
│   │   └── settings.json        # Timeouts, default years, and output paths
│   ├── src/
│   │   └── main.py              # Main downloader engine
│   ├── input.xlsx               # Excel list with District & Assembly Constituency columns
│   ├── requirements.txt         # Python dependencies
│   ├── setup.bat                # Windows setup script
│   ├── run.bat                  # Windows launch script
│   ├── README.md                # Project documentation
│   └── .gitignore               # Environment and artifact ignore rules
```

---

## Prerequisites

- **Python 3.11+**
- **Git**

---

## Quick Setup & Installation

### Windows Setup Script
1. Double-click `setup.bat` or run in terminal:
   ```cmd
   setup.bat
   ```

### Manual Setup
```bash
# 1. Create and activate virtual environment
python -m venv .venv
# On Windows:
call .venv\Scripts\activate.bat
# On Linux/macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Install Playwright Chromium browser
python -m playwright install chromium
```

---

## Usage

### Run via Command Line

```powershell
# Download for specific election years (e.g., 2023 and 2018)
python -m src.main --excel input.xlsx --years 2023 2018

# Run in visible browser mode
python -m src.main --excel input.xlsx --years 2023 --headed

# Run dry-run test (without downloading files)
python -m src.main --excel input.xlsx --years 2023 --dry-run
```

---

## Input Excel Schema

`input.xlsx` should contain a sheet named `Sheet1` with the following columns:

| S.No. | Seat No. | District | Assembly Constituency |
|-------|----------|----------|-----------------------|
| 1     | 1        | Sheopur  | Sheopur               |
| 2     | 2        | Sheopur  | Vijaypur              |

---

## Output Organization

Downloaded PDFs and execution logs are saved as follows:

```text
downloads/
  2023/
    Sheopur/
      1_Sheopur.pdf
      2_Vijaypur.pdf
  2018/
    Sheopur/
      1_Sheopur.pdf
logs/
  download_log.csv
```

---

## Pushing to GitHub

To initialize git and push to your GitHub repository:

```bash
git init
git add .
git commit -m "Initial commit: MP CEO Election PDF Downloader Bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```
