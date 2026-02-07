import os
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

import requests
from dotenv import load_dotenv
from requests import Session
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

BASE_URL = "https://forums.playdeadlock.com"
LOGIN_URL = f"{BASE_URL}/login"
LOGIN_POST_URL = f"{BASE_URL}/login/login"
TARGET_URL = f"{BASE_URL}/threads/doorman-permaban-bug-id-53130683.101983"

USERNAME = os.getenv("FORUM_USER") or os.getenv("USER") or "thebomb665"
PASSWORD = os.getenv("FORUM_PASS") or os.getenv("PASS") or "XXXX"

REQUEST_TIMEOUT = 15
PAGE_LOAD_TIMEOUT = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DAY_FILE = Path("day.txt")
DAY_INCREMENT = Decimal("0.25")


def read_day_value(path: Path) -> Decimal:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Decimal("0")

    cleaned = raw.replace("\x00", "").strip()
    if not cleaned:
        return Decimal("0")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise RuntimeError(f"Invalid day value in {path}: {cleaned!r}") from exc


def write_day_value(path: Path, value: Decimal) -> None:
    path.write_text(str(value), encoding="utf-8")


def fetch_login_token(session: Session) -> str:
    """Load the login page to collect the CSRF token the form requires."""
    response = session.get(LOGIN_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    match = re.search(r'name="_xfToken"\s+value="([^"]+)"', response.text)
    if not match:
        raise RuntimeError("Could not find _xfToken on the login page; layout may have changed.")

    return match.group(1)


def send_login_request(password: str) -> Session:
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    xf_token = fetch_login_token(session)
    form_data = {
        "_xfToken": xf_token,
        "login": USERNAME,
        "password": password,
        "remember": "1",
        "_xfRedirect": f"{BASE_URL}/",
    }

    response = session.post(
        LOGIN_POST_URL,
        data=form_data,
        timeout=REQUEST_TIMEOUT,
        headers={
            "Referer": LOGIN_URL,
            "Origin": BASE_URL,
        },
        allow_redirects=True,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Login POST failed: {response.status_code} {response.reason}; snippet: {response.text[:200]!r}"
        ) from exc

    if "xf_user" not in session.cookies:
        # Try to surface any inline error the login form returned (bad creds, captcha, etc.)
        error = re.search(
            r'class="formRow[^>]*formRow--error"[^>]*>\s*<dd[^>]*>\s*<ul[^>]*>\s*<li[^>]*>(.*?)<',
            response.text,
            re.S,
        )
        error_text = error.group(1).strip() if error else "No error message found."
        raise RuntimeError(
            f"Login may have failed; xf_user cookie not found. Last URL: {response.url}. Error text: {error_text}"
        )

    return session


def push_cookies_to_driver(driver: webdriver.Chrome, cookies: Iterable[requests.cookies.Cookie]) -> None:
    driver.get(BASE_URL)
    for cookie in cookies:
        if cookie.domain not in ("", "forums.playdeadlock.com", ".forums.playdeadlock.com"):
            continue
        driver.add_cookie(
            {
                "name": cookie.name,
                "value": cookie.value,
                "path": cookie.path,
                "domain": cookie.domain or "forums.playdeadlock.com",
            }
        )


def main() -> None:
    session = send_login_request(PASSWORD)

    options = Options()
    options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        push_cookies_to_driver(driver, session.cookies)

        driver.get(TARGET_URL)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"Loaded (post-login): {driver.title}")

        day_value = read_day_value(DAY_FILE)
        replyInput = driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/div/div[2]/div[3]/div/form/div/div/div/div/div[2]/div/div[1]/div[2]/div")
        replyInput.send_keys(f"Bump, day {day_value}")
        write_day_value(DAY_FILE, day_value + DAY_INCREMENT)

        replySubmit = driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/div/div[2]/div[3]/div/form/div/div/div/div/div[2]/div/div[3]/div[1]/button/span")
        replySubmit.click()

        print(f"Bumped @ {time.time()}")
    finally:
        driver.quit()



if __name__ == "__main__":
    while True:
        main()
        print("Sleeping")
        # 6 hours
        time.sleep(21600)
