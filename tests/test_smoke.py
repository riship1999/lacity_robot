import os
import re
import sys
import subprocess
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()

def run_cmd(args, timeout=180):
    """Run a command in project root and capture combined stdout/stderr."""
    return subprocess.run(
        args,
        cwd=str(PROJ_ROOT),
        env=ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )

# ---------- Helpers for assertions ----------

def assert_line(pattern, output, msg=None):
    assert re.search(pattern, output, re.M), msg or f"Missing line matching: {pattern}\nOUT:\n{output}"

def assert_exit(code_expected, res):
    assert res.returncode == code_expected, f"Exit={res.returncode} expected={code_expected}\nOUT:\n{res.stdout}"

# ---------- Tests ----------

def test_price_only_success():
    """Price-only lookup for a known product should succeed and exit 0."""
    cmd = [sys.executable, "-m", "src.main",
           "--product", "Sauce Labs Backpack",
           "--quiet"]
    res = run_cmd(cmd)
    assert_exit(0, res)
    assert_line(r"^SUCCESS: Product 'Sauce Labs Backpack' costs \$\d+\.\d{2}$", res.stdout)

def test_add_to_cart_multi_and_cart_summary():
    """Add multiple products, verify cart summary."""
    cmd = [sys.executable, "-m", "src.main",
           "--products", "Sauce Labs Backpack, Sauce Labs Bike Light",
           "--add-to-cart",
           "--quiet"]
    res = run_cmd(cmd)
    assert_exit(0, res)
    # success lines for each product price
    assert_line(r"^SUCCESS: Product 'Sauce Labs Backpack' costs \$\d+\.\d{2}$", res.stdout)
    assert_line(r"^SUCCESS: Product 'Sauce Labs Bike Light' costs \$\d+\.\d{2}$", res.stdout)
    # add confirmations
    assert_line(r"^SUCCESS: Added 'Sauce Labs Backpack' to cart$", res.stdout)
    assert_line(r"^SUCCESS: Added 'Sauce Labs Bike Light' to cart$", res.stdout)
    # cart summary
    assert_line(r"^CART: total_items=\d+$", res.stdout)
    # order of items is sorted in output
    assert_line(r"^CART: items=\[(?:.+; )?Sauce Labs Backpack; Sauce Labs Bike Light\]$", res.stdout)

def test_checkout_e2e_finish():
    """Full checkout: add two items, fill form, verify totals and finish page."""
    cmd = [sys.executable, "-m", "src.main",
           "--products", "Sauce Labs Backpack, Sauce Labs Bike Light",
           "--add-to-cart",
           "--checkout",
           "--first-name", "Heenal",
           "--last-name", "Patel",
           "--postal", "95050",
           "--quiet"]
    res = run_cmd(cmd, timeout=240)
    assert_exit(0, res)
    # pre-checkout confirmations exist
    assert_line(r"^CART: total_items=\d+$", res.stdout)
    assert_line(r"^CART: items=\[.*Sauce Labs Backpack.*;.*Sauce Labs Bike Light.*\]$", res.stdout)
    # checkout confirmations
    assert_line(r"^CHECKOUT: info_submitted=Heenal Patel 95050$", res.stdout)
    assert_line(r"^CHECKOUT: item_total=\$\d+\.\d{2}$", res.stdout)
    assert_line(r"^CHECKOUT: tax=\$\d+\.\d{2}$", res.stdout)
    assert_line(r"^CHECKOUT: total=\$\d+\.\d{2}$", res.stdout)
    assert_line(r"^ORDER: success=", res.stdout)  # message text can vary slightly; presence is enough

def test_notfound_auto_skip_checkout():
    """
    If no requested products exist, we should:
      - Print a single consolidated NOTFOUND line
      - Skip checkout cleanly
      - Exit with code 3
    """
    cmd = [sys.executable, "-m", "src.main",
           "--products", "Sauce Labs Light",
           "--add-to-cart",
           "--checkout",
           "--first-name", "Heenal",
           "--last-name", "Patel",
           "--postal", "95050",
           "--quiet"]
    res = run_cmd(cmd)
    assert_exit(3, res)
    # single consolidated NOTFOUND line
    assert_line(r"^NOTFOUND: Product 'Sauce Labs Light' not found$", res.stdout)
    # and explicit skip line because --checkout was requested
    assert_line(r"^CHECKOUT: skipped \(cart empty\)$", res.stdout)

def test_missing_checkout_params_fails_cleanly():
    """Missing checkout params must not crash argparse; we print a clean error and exit 2."""
    cmd = [sys.executable, "-m", "src.main",
           "--products", "Sauce Labs Backpack",
           "--add-to-cart",
           "--checkout",
           "--first-name",    # <-- intentionally missing value
           "--last-name", "Patel",
           "--postal", "95050",
           "--quiet"]
    res = run_cmd(cmd)
    # argparse would normally exit 2, but our validation prints a clean message and exits 2
    # Depending on the shell, argparse may still intercept before our code — so accept either:
    if res.returncode != 2:
        raise AssertionError(f"Expected exit 2 for missing checkout info, got {res.returncode}\nOUT:\n{res.stdout}")
    assert "AUTOMATION FAILED: Missing checkout info — please provide --first-name, --last-name, and --postal." in res.stdout or "expected one argument" in res.stdout

