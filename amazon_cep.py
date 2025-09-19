import os
import json
import time
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from telegram_cep import send_message

URL = "https://www.amazon.com.tr/s?i=electronics&rh=n%3A13709927031%2Cp_6%3AA1UNQM1SR2CHM%257CA215JX4S9CANSO&s=price-asc-rank&dc=&low-price=330&high-price=20500"
COOKIE_FILE = "cookie_cep.json"
SENT_FILE = "send_products.txt"

def decode_cookie_from_env():
    cookie_b64 = os.getenv("COOKIE_B64")
    if not cookie_b64:
        print("❌ COOKIE_B64 bulunamadı.")
        return False
    try:
        decoded = base64.b64decode(cookie_b64)
        with open(COOKIE_FILE, "wb") as f:
            f.write(decoded)
        print("✅ Cookie dosyası oluşturuldu.")
        return True
    except Exception as e:
        print(f"❌ Cookie decode hatası: {e}")
        return False

def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        print("❌ Cookie dosyası eksik.")
        return
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    for cookie in cookies:
        try:
            driver.add_cookie({
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie.get("path", "/")
            })
        except Exception as e:
            print(f"⚠️ Cookie eklenemedi: {cookie.get('name')} → {e}")

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_price_from_detail(driver, url):
    try:
        driver.get(url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )
        time.sleep(2)

        try:
            variant_input = driver.find_element(By.CSS_SELECTOR, "input.a-button-input[aria-checked='true']")
            driver.execute_script("arguments[0].click();", variant_input)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".aok-offscreen"))
            )
            time.sleep(1)
        except:
            pass

        price_elements = driver.find_elements(By.CSS_SELECTOR, ".aok-offscreen")
        for el in price_elements:
            text = el.get_attribute("innerText").strip()
            if "TL" in text and any(char.isdigit() for char in text):
                return text

        return "Fiyat alınamadı"
    except Exception as e:
        print(f"⚠️ Detay sayfasından fiyat alınamadı: {e}")
        return "Fiyat alınamadı"

def load_sent_data():
    data = {}
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|", 1)
                if len(parts) == 2:
                    asin, price = parts
                    data[asin.strip()] = price.strip()
    return data

def save_sent_data(products_to_send):
    existing = load_sent_data()
    for product in products_to_send:
        asin = product['asin'].strip()
        price = product['price'].strip()
        existing[asin] = price
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        for asin, price in existing.items():
            f.write(f"{asin} | {price}\n")

def run():
    if not decode_cookie_from_env():
        return

    driver = get_driver()
    driver.get("https://www.amazon.com.tr")
    time.sleep(2)
    load_cookies(driver)
    driver.get(URL)

    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-component-type='s-search-result']"))
        )
    except:
        print("⚠️ Sayfa yüklenemedi.")
        driver.quit()
        return

    items = driver.find_elements(By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
    print(f"🔍 {len(items)} ürün bulundu.")

    product_links = []
    for item in items:
        try:
            asin = item.get_attribute("data-asin")
            title = item.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("alt").strip()
            link = item.find_element(By.CSS_SELECTOR, "a.a-link-normal").get_attribute("href")
            image = item.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("src")
            product_links.append({
                "asin": asin,
                "title": title,
                "link": link,
                "image": image
            })
        except Exception as e:
            print("⚠️ Listeleme parse hatası:", e)
            continue

    products = []
    for product in product_links:
        try:
            price = get_price_from_detail(driver, product["link"])
            product["price"] = price
            products.append(product)
        except Exception as e:
            print("⚠️ Detay sayfa hatası:", e)
            continue

    driver.quit()

    sent_data = load_sent_data()
    products_to_send = []

    for product in products:
        asin = product["asin"]
        price = product["price"].strip()

        if asin in sent_data:
            old_price = sent_data[asin]
            if price != old_price:
                print(f"📉 Fiyat düştü: {product['title']} → {old_price} → {price}")
                products_to_send.append(product)
        else:
            print(f"🆕 Yeni ürün: {product['title']}")
            products_to_send.append(product)

    if products_to_send:
        for p in products_to_send:
            send_message(p)
        save_sent_data(products_to_send)
        print(f"📁 Dosya güncellendi: {len(products_to_send)} ürün eklendi/güncellendi.")
    else:
        print("⚠️ Yeni veya indirimli ürün bulunamadı.")

if __name__ == "__main__":
    run()