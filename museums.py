from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import requests
from bs4 import BeautifulSoup
import os

# --- Selenium setup ---
options = Options()
options.add_argument("--headless")          # run browser in background
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# --- Open page ---
url = "https://www.museum.nl/nl/zien-en-doen/musea?mv-PageIndex=0"
driver.get(url)
time.sleep(3)

print("🌐 Page loaded, starting to click 'Laad meer'...")

# --- Keep clicking "Laad meer" until it's gone ---
while True:
    try:
        load_more = driver.find_element(By.CSS_SELECTOR, ".tiles-block_load-more button.btn-default")
        driver.execute_script("arguments[0].scrollIntoView(true);", load_more)
        driver.execute_script("arguments[0].click();", load_more)
        print("🔄 Loading more museums...")
        time.sleep(3)
    except NoSuchElementException:
        print("✅ No more museums to load.")
        break
    except ElementClickInterceptedException:
        print("⚠️ Could not click 'Laad meer' this round, retrying...")
        time.sleep(2)
        continue

# --- Parse all museum cards ---
cards = driver.find_elements(By.CSS_SELECTOR, ".see-and-do-card")

museums = []
output_file = "museums.json"

# If file exists (resuming), load existing progress
if os.path.exists(output_file):
    with open(output_file, "r", encoding="utf-8") as f:
        try:
            museums = json.load(f)
        except json.JSONDecodeError:
            museums = []

print(f"🔍 Found {len(cards)} museum cards. Scraping details...")

for i, card in enumerate(cards, start=1):
    try:
        # --- Extract link from the card ---
        link_elem = card.find_element(By.CSS_SELECTOR, "a")
        partial_link = link_elem.get_attribute("href")
        link = "https://www.museum.nl" + partial_link if partial_link.startswith("/") else partial_link

        # --- Fetch detail page ---
        res = requests.get(link)
        soup = BeautifulSoup(res.text, "html.parser")

        # --- Use <h1> as title ---
        h1_tag = soup.find("h1")
        name = h1_tag.get_text(strip=True) if h1_tag else "Unknown"

        # --- Thumbnail from overview card ---
        img_elem = card.find_element(By.CSS_SELECTOR, "img")
        thumbnail = img_elem.get_attribute("src") if img_elem else None

        # --- Extract and clean address ---
        address_tag = soup.select_one("section.practical-info address")
        if address_tag:
            for child in address_tag.find_all(["a", "svg", "strong", "span"]):
                child.decompose()
            location = address_tag.get_text(separator=" ", strip=True)
        else:
            location = "Unknown"

        museum_data = {
            "name": name,
            "thumbnail": thumbnail,
            "link": link,
            "location": location
        }

        museums.append(museum_data)

        # --- Save progress live ---
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(museums, f, ensure_ascii=False, indent=2)

        print(f"[{i}/{len(cards)}] ✅ {name} — {location}")

    except Exception as e:
        print(f"[{i}/{len(cards)}] ⚠️ Error scraping card: {e}")

driver.quit()

print(f"\n🎉 Done! Saved {len(museums)} museums to {output_file}")
