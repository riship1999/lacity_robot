from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from rich.console import Console
import sys

console = Console()

def main() -> int:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Go to a lightweight, stable page
            page.set_default_timeout(7000)  # 7s default per action
            page.goto("https://example.com", wait_until="domcontentloaded")

            # Minimal validation so we know automation works
            title = page.title()
            console.log(f"[bold]Visited[/] https://example.com | Title: '{title}'")

            browser.close()
        console.print("[green]HEALTHCHECK PASSED[/]")
        return 0
    except PWTimeoutError as e:
        console.print(f"[red]TIMEOUT:[/] {e}")
    except Exception as e:
        console.print(f"[red]UNEXPECTED ERROR:[/] {e}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
