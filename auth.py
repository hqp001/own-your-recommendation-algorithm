"""One-time manual login: opens a headed browser, waits for you to log in,
then saves the session (cookies/local storage) so run.py can reuse it
without ever storing your password.

Usage:
    python auth.py
"""

from playwright.sync_api import sync_playwright

from config import load_config

X_LOGIN_URL = "https://x.com/login"


def main() -> None:
    cfg = load_config()

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(X_LOGIN_URL)

        print("A browser window has opened.")
        print("Log in to X normally (including any 2FA prompts).")
        input("Once you see your home timeline, come back here and press Enter... ")

        context.storage_state(path=cfg["auth_state_file"])
        browser.close()

    print(f"Session saved to {cfg['auth_state_file']}. You can now run: python run.py")


if __name__ == "__main__":
    main()
