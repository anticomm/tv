import os
import json
import time
import base64
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from telegram_cep import send_message

URL = "https://www.amazon.com.tr/s?k=televizyon&i=electronics&bbn=44219324031&rh=n%3A12466496031%2Cn%3A44219324031%2Cn%3A13709882031%2Cn%3A137099"
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
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_used_price_from_item(item):
    try:
        container = item.find_element(
            By.XPATH,
            ".//span[contains(text(), 'Diğer satın alma seçenekleri')]/following::span[contains(text(), 'TL')][1]"
        )
        price = container.text.strip()
        return price
    except:
        return None

def get_used_price_from_detail(driver):
    try:
        container = driver.find_element(
            By.XPATH,
            "//div[contains(@class, 'a-column') and .//span[contains(text(), 'İkinci El Ürün Satın Al:')]]"
        )
        price_element = container.find_element(By.CLASS_NAME, "offer-price")
        price = price_element.text.strip()
        return price
    except:
        return None

def get_final_price(driver, link):
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[1])
        driver.get(link)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        price = get_used_price_from_detail(driver)
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return price
    except Exception as e:
        print(f"⚠️ Detay sayfa hatası: {e}")
        try:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except:
            pass
        return None

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

def save_sent_data(updated_data):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        for asin, price in updated_data.items():
            f.write(f"{asin} | {price}\n")

def run():
    if not decode_cookie_from_env():
        return

    driver = get_driver()
    driver.get(URL)
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

    driver.execute_script("""
      document.querySelectorAll("h5.a-carousel-heading").forEach(h => {
        let box = h.closest("div");
        if (box) box.remove();
      });
    """)

    items = driver.find_elements(By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
    print(f"🔍 {len(items)} ürün bulundu.")
    products = []
    for item in items:
        try:
            if item.find_elements(By.XPATH, ".//span[contains(text(), 'Sponsorlu')]"):
                continue

            asin = item.get_attribute("data-asin")
            if not asin:
                continue

            title = item.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("alt").strip()
            link = item.find_element(By.CSS_SELECTOR, "a.a-link-normal").get_attribute("href")
            image = item.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("src")

            price = get_used_price_from_item(item)
            if not price:
                price = get_final_price(driver, link)

            if not price:
                continue

            products.append({
                "asin": asin,
                "title": title,
                "link": link,
                "image": image,
                "price": price
            })

        except Exception as e:
            print(f"⚠️ Ürün parse hatası: {e}")
            continue

    driver.quit()
    print(f"✅ {len(products)} ürün başarıyla alındı.")

    sent_data = load_sent_data()
    products_to_send = []

    for product in products:
        asin = product["asin"]
        price = product["price"].strip()

        if asin in sent_data:
            old_price = sent_data[asin]
            try:
                old_val = float(old_price.replace("TL", "").replace(".", "").replace(",", ".").strip())
                new_val = float(price.replace("TL", "").replace(".", "").replace(",", ".").strip())
            except:
                print(f"⚠️ Fiyat karşılaştırılamadı: {product['title']} → {old_price} → {price}")
                sent_data[asin] = price
                continue

            if new_val < old_val:
                print(f"📉 Fiyat düştü: {product['title']} → {old_price} → {price}")
                product["old_price"] = old_price
                products_to_send.append(product)
            else:
                print(f"⏩ Fiyat yükseldi veya aynı: {product['title']} → {old_price} → {price}")
            sent_data[asin] = price

        else:
            print(f"🆕 Yeni ürün: {product['title']}")
            products_to_send.append(product)
            sent_data[asin] = price

    if products_to_send:
        for p in products_to_send:
            send_message(p)
        save_sent_data(sent_data)
        print(f"📁 Dosya güncellendi: {len(products_to_send)} ürün eklendi/güncellendi.")
    else:
        print("⚠️ Yeni veya indirimli ürün bulunamadı.")

if __name__ == "__main__":
    run()
