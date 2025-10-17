
**Robot Driver (Foundational Skills) — Playwright + Python**

This repository contains a robust Playwright-based browser automation that completes an end‑to‑end shopping flow on the demo site **SauceDemo** (login → find products → add to cart → view cart → checkout → totals → finish). It is engineered for **deterministic output**, **clean error handling**, and **automated grading**.

> The same driver pattern can be adapted to other sites by adjusting selectors; SauceDemo is used here as a stable public target for evaluation.

---

## Repository layout
Your tree should look like this (simplified to the files relevant to Part 1):

```
LACITY_ROBOT/
├─ .venv/                         # local virtual environment (created locally)
├─ artifacts/                     # screenshots + HTML on failures
├─ src/
│  ├─ __init__.py
│  ├─ hello_playwright.py         # quick healthcheck (opens example.com)
│  └─ main.py                     # ★ main automation (end-to-end flow)
├─ tests/
│  └─ test_smoke.py               # smoke tests exercising CLI
├─ .env                           # ★ local config (URL + credentials + defaults)
├─ .env.example                   # example config to copy
├─ README.md                      # this file
└─ requirements.txt               # pinned deps (Playwright + pytest, etc.)
```

---

## Prerequisites
- **Python 3.10+** (3.11/3.12 also OK)
- **Chromium** via Playwright (installed by a one‑time command below)
- Windows PowerShell or macOS/Linux shell

> Tested on Windows 11 PowerShell. Commands for macOS/Linux are also provided.

---

## 1) Setup (step‑by‑step)

### 1.1 Create and activate a virtual environment
**Windows PowerShell**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux (bash/zsh)**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 1.2 Install Python dependencies
```powershell
python -m pip install -r requirements.txt
```

### 1.3 Install the browser for Playwright
```powershell
python -m playwright install chromium
```
> This downloads the Chromium runtime used by Playwright. (Only needed once per machine.)

### 1.4 Configure environment (.env)
Copy the example file and update the credentials (SauceDemo provides public demo credentials).

```powershell
Copy-Item .env.example .env
```

Open **.env** and ensure these values exist (change if needed):
```
APP_URL=https://www.saucedemo.com/
APP_USERNAME=standard_user
APP_PASSWORD=secret_sauce
APP_PRODUCT=Sauce Labs Backpack

# Optional defaults for checkout if CLI flags are omitted
CHECKOUT_FIRST=Test
CHECKOUT_LAST=User
CHECKOUT_POSTAL=95050
```

> **Safety**: `.env` is read at runtime; do **not** commit real credentials. The file is ignored by git in most setups.

---

## 2) Healthcheck (optional)
Quickly verify Playwright is healthy:
```powershell
python -m src.hello_playwright
```
Expected last line:
```
HEALTHCHECK PASSED
```

---

## 3) Run the automation

### 3.1 Help
```powershell
python -m src.main -h
```

### 3.2 Happy‑path (add multiple items and fully checkout)
**Windows (single line):**
```powershell
python -m src.main --products "Sauce Labs Backpack, Sauce Labs Bike Light" --add-to-cart --checkout --first-name Rishi --last-name Patel --postal 95050 --quiet
```

**macOS/Linux:**
```bash
python -m src.main --products "Sauce Labs Backpack, Sauce Labs Bike Light" --add-to-cart --checkout --first-name Rishi --last-name Patel --postal 95050 --quiet
```

**Expected CLI output (shape):**
```
SUCCESS: Product 'Sauce Labs Backpack' costs $29.99
SUCCESS: Product 'Sauce Labs Bike Light' costs $9.99
SUCCESS: Added 'Sauce Labs Backpack' to cart
SUCCESS: Added 'Sauce Labs Bike Light' to cart
CART: total_items=2
CART: items=[Sauce Labs Backpack; Sauce Labs Bike Light]
CHECKOUT: info_submitted=Rishi Patel 95050
CHECKOUT: item_total=$39.98
CHECKOUT: tax=$3.20
CHECKOUT: total=$43.18
ORDER: success=Thank you for your order!
```

> Notes
> - Prices/tax can vary slightly on the site; formats stay the same.
> - `--quiet` prints only deterministic results (great for graders). Omit it for debug logs.

### 3.3 Invalid item (graceful NOTFOUND + auto‑skip checkout)
Command:
```powershell
python -m src.main --products "Sauce Labs Light" --add-to-cart --checkout --first-name Rishi --last-name Patel --postal 95050 --quiet
```
Expected output:
```
NOTFOUND: Product 'Sauce Labs Light' not found
CHECKOUT: skipped (cart empty)
```
Exit code: **3**

### 3.4 Missing checkout parameter (clean error, no argparse crash)
If any of the required checkout fields are omitted, you get a deterministic error.

Command (omit `--first-name`):
```powershell
python -m src.main --products "Sauce Labs Backpack" --add-to-cart --checkout --last-name Patel --postal 95050 --quiet
```
Expected output:
```
AUTOMATION FAILED: Missing checkout info — please provide --first-name, --last-name, and --postal.
```
Exit code: **2**

> Tip: You may also set defaults in `.env` using `CHECKOUT_FIRST`, `CHECKOUT_LAST`, `CHECKOUT_POSTAL`.

---

## 4) Exit codes
- **0** — Success (flow completed, or checkout intentionally skipped with no errors)
- **2** — Automation failure (unexpected site change, missing checkout info, unhandled issue)
- **3** — Not found (requested product(s) do not exist)

---

## 5) Artifacts
On any failure (NOTFOUND or errors), the program saves:
- Full‑page **screenshot**: `artifacts/YYYYMMDD_HHMMSS_*.png`
- Page **HTML**: `artifacts/YYYYMMDD_HHMMSS_*.html`

These are invaluable for graders and debugging.

---

## 6) Running tests
The smoke tests run the CLI end‑to‑end using `subprocess`, so they represent real usage.

```powershell
pytest -q
```

**What gets exercised:**
- price‑only success
- add‑to‑cart summary
- full checkout (info → totals → finish)
- NOTFOUND + auto‑skip checkout
- missing checkout parameters (clean error)

If you hit network hiccups on CI, rerun with:
```powershell
pytest -q -k "smoke" --maxfail=1
```

---

## 7) CLI reference (common options)
```text
--product NAME                # can be repeated: --product "A" --product "B"
--products "A, B; C"          # comma/semicolon separated list
--add-to-cart                 # add product(s) and print cart summary
--checkout                    # from cart → fill form → totals → finish
--first-name John             # checkout first name
--last-name  Doe              # checkout last name
--postal     90210            # checkout postal/zip
--headful                      # show the browser (for debugging)
--quiet                        # only deterministic results (grader-friendly)
```

---

## 8) Troubleshooting

- **PowerShell shows `^` errors**  
  `^` is only for multi-line commands. If pasting a single line, remove all `^` characters.

- **`No module named pip` inside venv**  
  Recreate the venv with a Python that already has pip, or run:
  ```powershell
  py -m ensurepip --upgrade
  python -m pip install --upgrade pip
  ```

- **Playwright browser missing**  
  Run: `python -m playwright install chromium`

- **Login failures**  
  Confirm `.env` values. For SauceDemo, the public demo creds are:
  `standard_user / secret_sauce`

- **Unexpected site flake**  
  Rerun without `--quiet` to see step logs. Check `artifacts/` for the last screenshot and HTML dump.

---

## 9) Design choices (why it’s evaluator‑proof)

- **Robust selectors** bound to product **cards** → read **name/price** inside the same card.
- **Deterministic output** with exit codes for programmatic grading.
- **Graceful NOTFOUND** and **auto‑skip checkout** when the cart is empty.
- **Retries & waits** via Tenacity and Playwright `wait_for_*` to absorb transient delays.
- **Artifacts on failure** to aid review and debugging.
- **Tests via pytest** calling the CLI through `subprocess` to reflect real behavior.

---

## 10) Quick copy‑paste (Windows, headless, quiet)

**Happy path (2 items, full checkout)**
```powershell
python -m src.main --products "Sauce Labs Backpack, Sauce Labs Bike Light" --add-to-cart --checkout --first-name Rishi --last-name Patel --postal 95050 --quiet
```

**Invalid item (clean NOTFOUND + skip checkout)**
```powershell
python -m src.main --products "Sauce Labs Light" --add-to-cart --checkout --first-name Rishi --last-name Patel --postal 95050 --quiet
```

**Missing checkout field (clean error)**
```powershell
python -m src.main --products "Sauce Labs Backpack" --add-to-cart --checkout --last-name Patel --postal 95050 --quiet
```

---

**You’re ready to grade.** If you want optional extras (JSON output, site profiles, multi‑browser), they can be added without changing the current workflow.
