import os
import re
import time
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

BASE_URL = "https://forums.playdeadlock.com"
LOGIN_URL = f"{BASE_URL}/login"
TARGET_URL = f"{BASE_URL}/threads/doorman-permaban-bug-id-53130683.101983"

USERNAME = os.getenv("FORUM_USER") or os.getenv("USER") or "thebomb665"
PASSWORD = os.getenv("FORUM_PASS") or os.getenv("PASS") or "XXXX"

REQUEST_TIMEOUT = 15
PAGE_LOAD_TIMEOUT = 30
HEADLESS = os.getenv("HEADLESS", "1") == "1"
CHROME_BIN = os.getenv("CHROME_BIN", "")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "")
CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", "/tmp/selenium-chrome-profile")
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


def resolve_chrome_binary() -> str:
    candidates = [
        CHROME_BIN,
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "Chrome/Chromium binary not found. Install it or set CHROME_BIN to its full path."
    )


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def resolve_chromedriver_path() -> str | None:
    if CHROMEDRIVER_PATH:
        return CHROMEDRIVER_PATH

    try:
        from chromedriver_py import binary_path
    except ImportError:
        return None

    return binary_path


def login_with_selenium(driver: webdriver.Chrome) -> None:
    driver.get(LOGIN_URL)

    if driver.get_cookie("xf_user"):
        return

    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.NAME, "login")))
    except TimeoutException as exc:
        raise RuntimeError("Login form did not load; possible challenge page or outage.") from exc

    user_field = driver.find_element(By.NAME, "login")
    pass_field = driver.find_element(By.NAME, "password")
    user_field.clear()
    user_field.send_keys(USERNAME)
    pass_field.clear()
    pass_field.send_keys(PASSWORD)
    pass_field.submit()

    try:
        WebDriverWait(driver, 15).until(lambda d: d.get_cookie("xf_user") is not None)
    except TimeoutException:
        error_els = driver.find_elements(
            By.CSS_SELECTOR,
            ".formRow--error li, .formRow--error .formRow-explain, .blockMessage--error",
        )
        messages = [el.text.strip() for el in error_els if el.text.strip()]
        error_text = messages[0] if messages else "No error message found."
        raise RuntimeError(
            f"Login may have failed; xf_user cookie not found. Last URL: {driver.current_url}. "
            f"Error text: {error_text}"
        )


def main() -> None:
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=0")
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument(f"--user-agent={DEFAULT_USER_AGENT}")
    ensure_dir(CHROME_PROFILE_DIR)
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    options.binary_location = resolve_chrome_binary()

    resolved_driver = resolve_chromedriver_path()
    service = Service(executable_path=resolved_driver) if resolved_driver else Service()
    try:
        driver = webdriver.Chrome(options=options, service=service)
    except WebDriverException as exc:
        message = str(exc)
        if "Status code was: 127" in message:
            raise RuntimeError(
                "ChromeDriver failed to start (status 127). This usually means missing system "
                "libraries or a missing Chrome/Chromium install inside the container. "
                "Install Chromium or set CHROME_BIN/CHROMEDRIVER_PATH explicitly."
            ) from exc
        raise
    try:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        login_with_selenium(driver)

        driver.get(TARGET_URL)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"Loaded (post-login): {driver.title}")

        day_value = read_day_value(DAY_FILE)
        replyInput = driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/div/div[2]/div[3]/div/form/div/div/div/div/div[2]/div/div[1]/div[2]/div")
        replyInput.send_keys(f"Bump, day {day_value}")
        # write_day_value(DAY_FILE, day_value + DAY_INCREMENT)
        #
        # replySubmit = driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/div/div[2]/div[3]/div/form/div/div/div/div/div[2]/div/div[3]/div[1]/button/span")
        # replySubmit.click()

        print(f"Bumped @ {time.time()}")
    finally:
        driver.quit()



if __name__ == "__main__":
    while True:
        main()
        print("Sleeping")
        # 6 hours
        time.sleep(21600)
