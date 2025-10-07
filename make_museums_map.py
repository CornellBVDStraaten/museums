import json
import os
import time
import html
import requests
import folium
from folium.plugins import MarkerCluster

# -----------------------------
# Config
# -----------------------------
INPUT_JSON = "museums.json"
CACHE_JSON = "geocode_cache.json"
OUTPUT_HTML = "museums_map.html"

MAP_CENTER = (52.2, 5.3)
ZOOM_START = 7
TILE_STYLE = "CartoDB dark_matter"

USER_AGENT = "museum-map-scraper/1.0 (contact: youremail@example.com)"
GEOCODE_SLEEP_SECONDS = 1.2
RETRY_BACKOFF_SECONDS = 5

# -----------------------------
# Helpers
# -----------------------------
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default
    return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def geocode_address(address, session, cache):
    if not address:
        return (None, None)
    if address in cache:
        return cache[address]
    coords = _geocode_nominatim(address, session)
    if coords == (None, None):
        coords = _geocode_nominatim(f"{address}, Netherlands", session)
    cache[address] = coords
    save_json(CACHE_JSON, cache)
    time.sleep(GEOCODE_SLEEP_SECONDS)
    return coords


def _geocode_nominatim(query, session):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = session.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code == 429:
            time.sleep(RETRY_BACKOFF_SECONDS)
            resp = session.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return (None, None)
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return (lat, lon)
    except requests.RequestException:
        return (None, None)


def build_popup_html(item, index):
    """Build popup with JS controls for 'visited' + review."""
    name = html.escape(item.get("name", "Unknown"))
    address = html.escape(item.get("location", "Unknown"))
    link = item.get("link", "")
    thumb = item.get("thumbnail", "")
    museum_id = f"museum_{index}"

    link_html = f'<a href="{html.escape(link)}" target="_blank" rel="noopener">Open pagina</a>' if link else ""
    img_html = f'<div style="margin-top:8px;"><img src="{html.escape(thumb)}" alt="" style="max-width:220px;height:auto;border-radius:8px;"></div>' if thumb else ""

    return f"""
    <div id="{museum_id}" style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 260px;">
      <div style="font-weight:600; font-size:14px; margin-bottom:4px;">{name}</div>
      <div style="font-size:13px; color:#333; margin-bottom:6px;">{address}</div>
      <div style="font-size:13px;">{link_html}</div>
      {img_html}
      <hr style="margin:8px 0;">
      <label style="font-size:13px;">
        <input type="checkbox" class="visited-toggle" data-id="{museum_id}"> Visited
      </label>
      <textarea class="review-box" data-id="{museum_id}" placeholder="Write a review..." style="width:100%;margin-top:4px;font-size:13px;"></textarea>
    </div>
    """


# -----------------------------
# Main
# -----------------------------
def main():
    museums = load_json(INPUT_JSON, [])
    if not museums:
        print(f"⚠️ No data found in {INPUT_JSON}.")
        return
    
    geocode_cache = load_json(CACHE_JSON, {})
    session = requests.Session()

    fmap = folium.Map(location=MAP_CENTER, zoom_start=ZOOM_START, tiles=TILE_STYLE)
    cluster = MarkerCluster(name="Musea").add_to(fmap)

    for i, item in enumerate(museums, start=1):
        name = item.get("name", "")
        address = item.get("location", "")
        lat = item.get("latitude")
        lon = item.get("longitude")

        if lat is None or lon is None:
            lat, lon = geocode_address(address, session, geocode_cache)
            item["latitude"] = lat
            item["longitude"] = lon
            save_json(INPUT_JSON, museums)

        if lat is None or lon is None:
            continue

        popup_html = build_popup_html(item, i)
        marker = folium.Marker(
            location=(lat, lon),
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=name,
            icon=folium.Icon(color="red", icon="info-sign")  # start unvisited = red
        )
        marker.add_to(cluster)
        print(f"✅ Added: {name}")

    # Inject JavaScript for localStorage visited + review persistence
    js_code = """
    <script>
    function applySavedState() {
    document.querySelectorAll('.visited-toggle').forEach(cb => {
        const id = cb.dataset.id;
        const state = localStorage.getItem(id + '_visited');
        if (state === 'true') cb.checked = true;
    });
    document.querySelectorAll('.review-box').forEach(tb => {
        const id = tb.dataset.id;
        const saved = localStorage.getItem(id + '_review');
        if (saved) tb.value = saved;
    });
    }

    function saveState(id) {
    const cb = document.querySelector('[data-id="' + id + '"].visited-toggle');
    const tb = document.querySelector('[data-id="' + id + '"].review-box');
    if (cb) localStorage.setItem(id + '_visited', cb.checked);
    if (tb) localStorage.setItem(id + '_review', tb.value);
    }

    // When a popup opens, restore its state
    document.addEventListener('popupopen', function() {
    setTimeout(applySavedState, 200);
    });

    // When user interacts with inputs, save immediately
    document.addEventListener('input', function(e) {
    if (e.target.classList.contains('visited-toggle') || e.target.classList.contains('review-box')) {
        const id = e.target.dataset.id;
        saveState(id);
    }
    });

    // On page load, prefill all visible popups (if any)
    window.addEventListener('load', applySavedState);
    </script>
    """

    fmap.get_root().html.add_child(folium.Element(js_code))

    fmap.save(OUTPUT_HTML)
    print(f"🎉 Map saved to {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
