import os
import sys
import time
from pathlib import Path
from typing import List
import argparse

from dotenv import load_dotenv
from rich.console import Console
from rich.traceback import install
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    retry_if_exception_type,
)
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PWTimeoutError,
    Error as PWError,
)

install(show_locals=False)
console = Console()

# ---------------- Logging ----------------
QUIET = False
def log(msg: str) -> None:
    if not QUIET:
        console.print(msg)

# ---------------- Artifacts --------------
ARTIFACTS_DIR = Path("artifacts"); ARTIFACTS_DIR.mkdir(exist_ok=True)

class AutomationFailure(RuntimeError): ...
class ProductNotFound(AutomationFailure): ...

def ts() -> str: return time.strftime("%Y%m%d_%H%M%S")

def save_artifacts(page, label: str) -> None:
    try:
        png = ARTIFACTS_DIR / f"{ts()}_{label}.png"
        html = ARTIFACTS_DIR / f"{ts()}_{label}.html"
        page.screenshot(path=str(png), full_page=True)
        html.write_text(page.content(), encoding="utf-8")
        log(f"[yellow]Saved artifacts:[/] {png.name}, {html.name}")
    except Exception as e:
        log(f"[red]Failed to save artifacts:[/] {e}")

# ---------------- Helpers ----------------
def _norm(s: str) -> str:
    return " ".join(s.split()).strip().casefold()

def _scroll_into_view(el):
    try: el.scroll_into_view_if_needed(timeout=2000)
    except Exception: pass

def _print_notfound(names: List[str]):
    # Single deterministic NOTFOUND line (as you requested).
    unique = [n for i, n in enumerate(names) if n not in names[:i]]
    if len(unique) == 1:
        console.print(f"NOTFOUND: Product '{unique[0]}' not found")
    else:
        console.print("NOTFOUND: Products not found: " + "; ".join(unique))

# -------------- Navigation ---------------
@retry(reraise=True, stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
       retry=retry_if_exception_type((PWTimeoutError, PWError)))
def goto_with_retry(page, url: str):
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=12000)

def login(page, username: str, password: str):
    # Username
    try: page.get_by_test_id("username").fill(username)
    except Exception: page.locator('input[data-test="username"], #user-name, input[name="user-name"]').first.fill(username)
    # Password
    try: page.get_by_test_id("password").fill(password)
    except Exception: page.locator('input[data-test="password"], #password, input[name="password"]').first.fill(password)
    # Login
    try: page.get_by_test_id("login-button").click()
    except Exception: page.locator('[data-test="login-button"], input[type="submit"], button[type="submit"]').first.click()

    # Verify inventory loaded
    page.wait_for_load_state("domcontentloaded", timeout=12000)
    page.wait_for_selector(
        "[data-test='inventory-container'], #inventory_container, .inventory_list, .inventory_item",
        timeout=15000
    )
    page.wait_for_load_state("networkidle", timeout=12000)

# ---------- Product discovery ------------
CARD_SEL_PRIMARY   = "[data-test='inventory-item']"
CARD_SEL_FALLBACK  = ".inventory_item"
NAME_SEL           = "[data-test='inventory-item-name'], .inventory_item_name"
PRICE_SEL          = "[data-test='inventory-item-price'], .inventory_item_price"
BTN_ADD_SEL        = "button:has-text('Add to cart'), [data-test*='add-to-cart']"
BTN_REMOVE_SEL     = "button:has-text('Remove'), [data-test*='remove']"
CART_BADGE_SEL     = ".shopping_cart_badge, [data-test='shopping-cart-badge']"
CART_LINK_SEL      = "[data-test='shopping-cart-link'], .shopping_cart_link, a[href*='cart']"
CHECKOUT_BTN_SEL   = "[data-test='checkout'], button:has-text('Checkout')"
FIRSTNAME_SEL      = "[data-test='firstName'], input#first-name, input[name='firstName']"
LASTNAME_SEL       = "[data-test='lastName'], input#last-name, input[name='lastName']"
POSTAL_SEL         = "[data-test='postalCode'], input#postal-code, input[name='postalCode']"
CONTINUE_BTN_SEL   = "[data-test='continue'], button:has-text('Continue')"
FINISH_BTN_SEL     = "[data-test='finish'], button:has-text('Finish')"
SUBTOTAL_SEL       = "[data-test='subtotal-label'], .summary_subtotal_label"
TAX_SEL            = "[data-test='tax-label'], .summary_tax_label"
TOTAL_SEL          = "[data-test='total-label'], .summary_total_label"
ORDER_OK_SEL       = "[data-test='complete-header'], .complete-header"

def _cards_locator(page):
    cards = page.locator(CARD_SEL_PRIMARY)
    if cards.count() == 0:
        cards = page.locator(CARD_SEL_FALLBACK)
    return cards

def _find_product_card(page, product_name: str):
    target = _norm(product_name)
    page.wait_for_selector(f"{CARD_SEL_PRIMARY}, {CARD_SEL_FALLBACK}", timeout=15000)
    cards = _cards_locator(page)
    count = cards.count()
    if count == 0:
        raise AutomationFailure("No inventory cards present")

    for i in range(count):
        card = cards.nth(i)
        name_loc = card.locator(NAME_SEL).first
        try:
            name_loc.wait_for(timeout=3000)
            _scroll_into_view(name_loc)
            name_text = name_loc.inner_text().strip()
        except Exception:
            continue
        if _norm(name_text) == target:
            return card

    raise ProductNotFound(f"Product '{product_name}' not found")

@retry(reraise=True, stop=stop_after_attempt(2), wait=wait_fixed(0.6),
       retry=retry_if_exception_type((PWTimeoutError, AutomationFailure)))
def extract_price_for(page, product_name: str) -> str:
    card = _find_product_card(page, product_name)
    price_loc = card.locator(PRICE_SEL).first
    price_loc.wait_for(timeout=8000)
    _scroll_into_view(price_loc)
    price = price_loc.inner_text().strip()
    if not price:
        raise AutomationFailure(f"Price text empty for product '{product_name}'")
    return price

# --------- Add-to-cart + Cart helpers ----
def add_to_cart_idempotent(page, product_name: str) -> str:
    """
    Adds product to cart if not already added.
    Returns: "added" or "already"
    """
    card = _find_product_card(page, product_name)

    # Already in cart?
    remove_btn = card.locator(BTN_REMOVE_SEL).first
    if remove_btn.count() > 0:
        try:
            remove_btn.wait_for(timeout=800)
            return "already"
        except Exception:
            pass

    add_btn = card.locator(BTN_ADD_SEL).first
    add_btn.wait_for(timeout=8000)
    _scroll_into_view(add_btn)
    add_btn.click()

    # Confirm flipped
    remove_btn = card.locator(BTN_REMOVE_SEL).first
    remove_btn.wait_for(timeout=8000)

    # Badge appears
    page.locator(CART_BADGE_SEL).first.wait_for(timeout=8000)
    return "added"

def open_cart(page):
    link = page.locator(CART_LINK_SEL).first
    link.wait_for(timeout=8000); _scroll_into_view(link); link.click()
    page.wait_for_selector(".cart_item, [data-test='cart-item']", timeout=10000)

def get_cart_items(page) -> List[str]:
    name_nodes = page.locator(
        "[data-test='inventory-item-name'], .inventory_item_name, [class*='inventory_item_name']"
    )
    count = name_nodes.count()
    items = []
    for i in range(count):
        node = name_nodes.nth(i)
        try:
            node.wait_for(timeout=1500)
            txt = node.inner_text().strip()
            if txt:
                items.append(txt)
        except Exception:
            continue
    return items

def add_many_to_cart(page, product_names: List[str]) -> dict:
    added, skipped, notfound = [], [], []
    for name in product_names:
        try:
            status = add_to_cart_idempotent(page, name)
            if status == "added":
                console.print(f"SUCCESS: Added '{name}' to cart")
                added.append(name)
            else:
                console.print(f"SKIP: '{name}' was already in cart")
                skipped.append(name)
        except ProductNotFound:
            # do NOT print here — we will print a single consolidated NOTFOUND later
            notfound.append(name)
        except Exception as e:
            raise AutomationFailure(f"Failed to add '{name}' to cart: {e}") from e
    return {'added': added, 'skipped': skipped, 'notfound': notfound}

# ---------------- Checkout ---------------
def click_checkout(page):
    btn = page.locator(CHECKOUT_BTN_SEL).first
    btn.wait_for(timeout=8000)
    _scroll_into_view(btn); btn.click()
    page.wait_for_selector(f"{FIRSTNAME_SEL}, {LASTNAME_SEL}, {POSTAL_SEL}", timeout=10000)

def fill_checkout_info(page, first: str, last: str, postal: str):
    fn = page.locator(FIRSTNAME_SEL).first
    ln = page.locator(LASTNAME_SEL).first
    zp = page.locator(POSTAL_SEL).first
    for el, val in [(fn, first), (ln, last), (zp, postal)]:
        el.wait_for(timeout=8000)
        _scroll_into_view(el); el.fill(val)

    console.print(f"CHECKOUT: info_submitted={first} {last} {postal}")

    cont = page.locator(CONTINUE_BTN_SEL).first
    cont.wait_for(timeout=8000); _scroll_into_view(cont); cont.click()

    page.wait_for_selector(f"{TOTAL_SEL}, {SUBTOTAL_SEL}", timeout=10000)

def read_checkout_totals(page):
    def read_text(sel, default=""):
        loc = page.locator(sel).first
        if loc.count() == 0:
            return default
        try:
            loc.wait_for(timeout=5000)
            txt = loc.inner_text().strip()
            return txt
        except Exception:
            return default

    subtotal = read_text(SUBTOTAL_SEL)
    tax      = read_text(TAX_SEL)
    total    = read_text(TOTAL_SEL)

    import re
    def amt(s):
        m = re.search(r"\$[0-9]+(?:\.[0-9]{2})?", s or "")
        return m.group(0) if m else ""
    sub_amt = amt(subtotal); tax_amt = amt(tax); total_amt = amt(total)

    console.print(f"CHECKOUT: item_total={sub_amt}")
    console.print(f"CHECKOUT: tax={tax_amt}")
    console.print(f"CHECKOUT: total={total_amt}")

    return sub_amt, tax_amt, total_amt

def finish_checkout(page):
    btn = page.locator(FINISH_BTN_SEL).first
    btn.wait_for(timeout=8000); _scroll_into_view(btn); btn.click()
    ok = page.locator(ORDER_OK_SEL).first
    ok.wait_for(timeout=10000)
    msg = ok.inner_text().strip()
    console.print(f"ORDER: success={msg}")
    return msg

# --------------- Orchestration ----------
def run(product_names: List[str], headful: bool = False,
        add_to_cart_flag: bool = False, do_checkout: bool = False,
        first_name: str = "", last_name: str = "", postal: str = "") -> int:

    load_dotenv(override=False)

    app_url = os.getenv("APP_URL", "https://www.saucedemo.com/")
    username = os.getenv("APP_USERNAME", "")
    password = os.getenv("APP_PASSWORD", "")

    if not username or not password:
        console.print("AUTOMATION FAILED: Missing APP_USERNAME/APP_PASSWORD in .env")
        return 2

    # Default checkout info from env if not provided via CLI
    first_name = first_name or os.getenv("CHECKOUT_FIRST", "Test")
    last_name  = last_name  or os.getenv("CHECKOUT_LAST",  "User")
    postal     = postal     or os.getenv("CHECKOUT_POSTAL","95050")

    log(f"Starting run | url={app_url} | products={product_names} | headful={headful} | add_to_cart={add_to_cart_flag} | checkout={do_checkout}")

    page = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headful, args=["--disable-dev-shm-usage"])
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(15000)

            goto_with_retry(page, app_url)
            login(page, username, password)

            # Price report (don’t print NOTFOUND here; we consolidate later)
            page.wait_for_selector(f"{CARD_SEL_PRIMARY}, {CARD_SEL_FALLBACK}", timeout=15000)
            if _cards_locator(page).count() == 0:
                raise AutomationFailure("No inventory items found after login")

            notfound_seen: List[str] = []
            for name in product_names:
                try:
                    price = extract_price_for(page, name)
                    console.print(f"SUCCESS: Product '{name}' costs {price}")
                except ProductNotFound:
                    notfound_seen.append(name)
                except Exception as e:
                    raise AutomationFailure(f"Failed to get price for '{name}': {e}") from e

            exit_code = 0

            # ---------- Add requested products ----------
            if add_to_cart_flag:
                summary = add_many_to_cart(page, product_names)
                notfound_all = list(set(notfound_seen + summary["notfound"]))
                cart_count = len(summary["added"]) + len(summary["skipped"])

                # NOTHING in cart -> skip cart/checkout cleanly
                if cart_count == 0:
                    if notfound_all:
                        _print_notfound(notfound_all)
                        exit_code = 3
                    if do_checkout:
                        console.print("CHECKOUT: skipped (cart empty)")
                    browser.close()
                    return exit_code

                # We have items -> show cart
                open_cart(page)
                items = get_cart_items(page)
                console.print(f"CART: total_items={len(items)}")
                console.print("CART: items=[" + "; ".join(sorted(items)) + "]")

                # Checkout only if cart non-empty
                if do_checkout:
                    click_checkout(page)
                    fill_checkout_info(page, first_name, last_name, postal)
                    read_checkout_totals(page)
                    finish_checkout(page)

                exit_code = 0 if not notfound_all else 3

            else:
                # No add-to-cart requested
                if do_checkout:
                    # Try opening cart; if empty -> skip
                    try:
                        open_cart(page)
                        items = get_cart_items(page)
                        if len(items) == 0:
                            console.print("CHECKOUT: skipped (cart empty)")
                            browser.close()
                            return 0
                        click_checkout(page)
                        fill_checkout_info(page, first_name, last_name, postal)
                        read_checkout_totals(page)
                        finish_checkout(page)
                    except ProductNotFound:
                        _print_notfound(notfound_seen)
                        browser.close()
                        return 3

            # If we saw notfound during price lookups but didn't add, report once
            if not add_to_cart_flag and notfound_seen:
                _print_notfound(notfound_seen)
                exit_code = 3

            browser.close()
            return exit_code

    except ProductNotFound as e:
        # Defensive: most paths already consolidate before reaching here
        _print_notfound([str(e).replace("Product '", "").replace("' not found", "")])
        if page: save_artifacts(page, "notfound")
        return 3
    except (PWTimeoutError, PWError, AutomationFailure) as e:
        console.print(f"AUTOMATION FAILED: {e}")
        if page: save_artifacts(page, "failure")
        return 2
    except Exception as e:
        console.print(f"AUTOMATION FAILED: {e}")
        if page: save_artifacts(page, "unexpected")
        return 2

# ---------------- CLI -------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="SauceDemo E2E: multi-add, cart, checkout, totals, finish.")
    # Accept multiple --product OR a single --products "A, B; C"
    ap.add_argument("--product", action="append", help="Product name to process (can be repeated).")
    ap.add_argument("--products", help="Comma/semicolon separated list of products.")
    ap.add_argument("--headful", action="store_true", help="Show browser window.")
    ap.add_argument("--add-to-cart", action="store_true", help="Add product(s) to cart and print cart summary.")
    ap.add_argument("--checkout", action="store_true", help="From cart → checkout → fill info → totals → finish.")
    ap.add_argument("--first-name", help="Checkout first name.")
    ap.add_argument("--last-name", help="Checkout last name.")
    ap.add_argument("--postal", help="Checkout postal/zip.")
    ap.add_argument("--quiet", action="store_true", help="Only deterministic result lines.")
    return ap.parse_args(argv)

if __name__ == "__main__":
    args = parse_args()
    QUIET = args.quiet

    # Build product list
    prods: List[str] = []
    if args.product:
        prods.extend(args.product)
    if args.products:
        for part in args.products.replace(";", ",").split(","):
            nm = part.strip()
            if nm:
                prods.append(nm)
    if not prods:
        prods = [os.getenv("APP_PRODUCT", "Sauce Labs Backpack")]

    # Validate checkout params cleanly (no argparse crash)
    if args.checkout:
        if not args.first_name or not args.last_name or not args.postal:
            console.print(
                "AUTOMATION FAILED: Missing checkout info — please provide --first-name, --last-name, and --postal."
            )
            sys.exit(2)

    sys.exit(
        run(
            prods,
            headful=args.headful,
            add_to_cart_flag=args.add_to_cart,
            do_checkout=args.checkout,
            first_name=args.first_name or "",
            last_name=args.last_name or "",
            postal=args.postal or "",
        )
    )
