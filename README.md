# 🤖 MP CEO Election PDF Downloader Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-2EAD33.svg?style=flat&logo=playwright&logoColor=white)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows | Linux | macOS](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue.svg)]()

An automated browser automation bot for downloading assembly election result PDFs (Form 20 and statistical reports) from the Chief Electoral Officer (CEO), Madhya Pradesh portal ([ceoelection.mp.gov.in](https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx)).

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Project Architecture](#-project-architecture)
- [Prerequisites](#-prerequisites)
- [Quick Start & Installation](#-quick-start--installation)
- [Excel Input Specification](#-excel-input-specification)
- [Usage & CLI Commands](#-usage--cli-commands)
- [Configuration](#-configuration)
- [Output Structure](#-output-structure)
- [Technical Solutions](#-technical-solutions)
- [Troubleshooting](#-troubleshooting)
- [License & Disclaimer](#-license--disclaimer)

---

## 🔍 Overview

The MP CEO election portal is built on **ASP.NET WebForms**, which dynamically loads assembly constituency data through server postbacks rather than exposing static URLs. This bot automates constituency lookup, dispatches required ASP.NET change events, matches constituency names phonetically, handles legacy government SSL certificates, and saves PDFs locally in a structured folder format.

---

## ✨ Key Features

- **ASP.NET WebForms Event Handling**: Interacts with cascading dropdowns (`ddlDist` / `ddlD` $\rightarrow$ `ddlAC`) and triggers ASP.NET `__doPostBack` events programmatically.
- **Phonetic & Fuzzy Name Matching**: Normalizes transliteration variations between Excel inputs and official dropdown values (e.g., `Sabalgarh` $\leftrightarrow$ `SABALAGADH`, `Joura` $\leftrightarrow$ `JAURA`, `Sumawali` $\leftrightarrow$ `SUMAOLI`, stripping `(SC)` / `(ST)` flags).
- **Legacy SSL Transport**: Utilizes a custom HTTP transport layer with `ssl.OP_LEGACY_SERVER_CONNECT` to bypass legacy OpenSSL renegotiation restrictions on government servers.
- **Resumable & Safe Operations**: Logs execution status (`DONE`, `SKIPPED`, `FAILED`) in `logs/download_log.csv` to ensure repeat runs skip already downloaded files seamlessly.
- **Headless & Headed Browser Modes**: Supports running in background mode or visible browser mode (`--headed`).

---

## 📁 Project Architecture

```text
PDF_Downloader_Bot/
├── config/
│   └── settings.json         # Timeouts, target years, and path configurations
├── src/
│   ├── __init__.py
│   └── main.py               # Core automation & download engine
├── input.xlsx                # Input Excel spreadsheet with District & Constituency list
├── requirements.txt          # Python dependencies
├── setup.bat                 # Automated Windows environment installer
├── run.bat                   # One-click launch script for Windows
├── README.md                 # Project documentation
└── .gitignore                # Git exclusion rules
```

---

## ⚙️ Prerequisites

- **Python**: Version 3.11 or higher
- **Git**: Installed on your system
- **Internet Access**: Active connection to reach `https://ceoelection.mp.gov.in`

---

## 🚀 Quick Start & Installation

### Option 1: Automatic Setup (Windows)

Simply double-click `setup.bat` or run:

```cmd
setup.bat
```

### Option 2: Manual Setup (Windows / Linux / macOS)

```bash
# 1. Clone the repository
git clone https://github.com/flerkenstudio/PDF_Downloader_Bot.git
cd PDF_Downloader_Bot

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate.bat

# Linux / macOS:
source .venv/bin/activate

# 3. Install required packages
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright browser binaries
python -m playwright install chromium
```

---

## 📊 Excel Input Specification

Place your target constituency list in `input.xlsx` (`Sheet1`). The file must include the following column headers:

| S.No. | Seat No. | District | Assembly Constituency |
| :--- | :--- | :--- | :--- |
| 1 | 1 | Sheopur | Sheopur |
| 2 | 2 | Sheopur | Vijaypur |
| 3 | 3 | Morena | Sabalgarh |
| 4 | 4 | Morena | Joura |

---

## 💻 Usage & CLI Commands

### 1. Default Run (2023 & 2018 Elections)

```bash
python -m src.main --excel input.xlsx --years 2023 2018
```

### 2. Visible Browser Mode (Headed)

Useful for observing browser navigation or handling CAPTCHA manually if prompted by the site:

```bash
python -m src.main --excel input.xlsx --years 2023 --headed
```

### 3. Dry-Run Mode

Simulates workflow and dropdown selection without downloading PDFs:

```bash
python -m src.main --excel input.xlsx --years 2023 --dry-run
```

### 4. Run via Batch Script (Windows)

```cmd
run.bat
```

---

## ⚙️ Configuration

Project settings are managed in `config/settings.json`:

```json
{
  "start_url": "https://ceoelection.mp.gov.in/ASSEMBLYELECTION.aspx",
  "download_root": "downloads",
  "log_file": "logs/download_log.csv",
  "browser": {
    "headless": false,
    "slow_mo_ms": 150
  },
  "timeouts": {
    "navigation_ms": 30000,
    "action_ms": 15000,
    "download_ms": 30000
  },
  "years": [2023, 2018, 2013, 2008, 2003],
  "manual_captcha_allowed": true
}
```

---

## 📂 Output Structure

All files are stored cleanly under the `downloads/` directory structured by election year and district name:

```text
downloads/
├── 2023/
│   ├── Sheopur/
│   │   ├── 1_Sheopur.pdf
│   │   └── 2_Vijaypur.pdf
│   └── Morena/
│       ├── 3_Sabalgarh.pdf
│       └── 4_Joura.pdf
└── 2018/
    └── Sheopur/
        └── 1_Sheopur.pdf

logs/
└── download_log.csv
```

---

## 🛠️ Technical Solutions

1. **ASP.NET PostBack Trigger**:
   Calling `.select_option()` alone does not fire inline `onchange` scripts in ASP.NET WebForms. The bot explicitly invokes `.dispatch_event("change")` on target `<select>` elements to initiate server postbacks cleanly.

2. **OpenSSL Legacy Renegotiation (`EPROTO`)**:
   Some state government portals run legacy IIS SSL configurations. The downloader uses a custom `ssl.SSLContext` with `OP_LEGACY_SERVER_CONNECT` enabled to guarantee stable file downloads.

3. **Unicode Console Compatibility**:
   Replaced special non-ASCII symbols with standard `OK` / `FAIL` status tags to ensure error-free console outputs across Windows Command Prompt (`cp1252`) and PowerShell environments.

---

## ❓ Troubleshooting

- **Server PostBack Times Out**: If the portal responds slowly, increase `navigation_ms` or `action_ms` in `config/settings.json`.
- **CAPTCHA Verification**: If the site presents a security check, execute with `--headed`. You can complete the verification manually in the browser window while the script continues execution.

---

## 📜 License & Disclaimer

Distributed under the **MIT License**.

> **Disclaimer**: This tool is developed strictly for public data aggregation and research purposes. Users must comply with the terms of use of the source website and avoid sending excessive rapid requests to public server infrastructure.
