import os
import time
import json
import base64
import requests
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from telegram_cep import send_epey_image, send_epey_link

def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title

def decode_cookie2_from_env():
    cookie_b64 = os.getenv("COOKIE2_B64")
    if not cookie_b64:
        print("❌ COOKIE2_B64 bulunamadı.")
        return False
    try:
        decoded = base64.b64decode(cookie_b64)
        with open("epey_cookie.json", "wb") as f:
            f.write(decoded)
        print("✅ Epey cookie dosyası oluşturuldu.")
        return True
    except Exception as e:
        print(f"❌ Cookie decode hatası: {e}")
        return False

def load_epey_cookies(driver):
    if not os.path.exists("epey_cookie.json"):
        print("⚠️ epey_cookie.json bulunamadı, cookie yüklenemedi.")
        return
    try:
        with open("epey_cookie.json", "r") as f:
            cookies = json.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        print("✅ Cookie tarayıcıya yüklendi.")
    except Exception as e:
        print(f"❌ Cookie yükleme hatası: {e}")

def get_driver():
    try:
        path = ChromeDriverManager().install()
        print(f"🧪 Chrome driver path: {path}")
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115 Safari/537.36")
        return webdriver.Chrome(service=Service(path), options=options)
    except WebDriverException as e:
        print(f"❌ WebDriver başlatılamadı: {e}")
        return None

def find_epey_link(product_name: str) -> str:
    print(f"🔍 Epey link sayfa üzerinden aranıyor: {product_name}")
    return find_epey_link_via_page(product_name)

def find_epey_link_via_page(product_name: str) -> str:
    query = f"{normalize_title(product_name)} epey"
    url = f"https://cse.google.com/cse?cx=44a7591784d2940f5&q={query.replace(' ', '+')}"
    driver = get_driver()
    if not driver:
        print("❌ Tarayıcı başlatılamadı, fallback link alınamadı")
        return None
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a")))
        links = driver.find_elements(By.CSS_SELECTOR, "a")
        for link in links:
            href = link.get_attribute("href")
            if href and "epey.com" in href:
                print(f"🔗 Sayfa üzerinden Epey link bulundu: {href}")
                driver.quit()
                return href
    except Exception as e:
        print(f"⚠️ Sayfa üzerinden Epey linki alınamadı: {e}")
    driver.quit()
    return None

def capture_epey_screenshot(url: str, save_path="epey.png"):
    driver = get_driver()
    if not driver:
        print("❌ Tarayıcı başlatılamadı, ekran görüntüsü atlanıyor")
        return None
    try:
        driver.get("https://www.epey.com/")
        decode_cookie2_from_env()
        load_epey_cookies(driver)
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(2)
        driver.save_screenshot(save_path)
        driver.quit()
        return save_path
    except Exception as e:
        print(f"⚠️ Epey ekran görüntüsü hatası: {e}")
        driver.quit()
        return None

def run_capture(product: dict):
    title = product["title"]
    asin = product.get("asin", "fallback")
    epey_url = find_epey_link(title)

    if epey_url:
        screenshot_path = capture_epey_screenshot(epey_url, save_path=f"epey_{asin}.png")
        if screenshot_path:
            send_epey_image(product, screenshot_path)
        else:
            print(f"⚠️ Epey sayfası açıldı ama ekran görüntüsü alınamadı: {epey_url}")
            send_epey_link(product, epey_url)
    else:
        search_url = f"https://cse.google.com/cse?cx=44a7591784d2940f5&q={normalize_title(title).replace(' ', '+')}+epey"
        send_epey_link(product, search_url)
