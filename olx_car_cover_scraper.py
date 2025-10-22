

import argparse
import csv
import json
import os
import re
import sys
import time
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Default headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

OUTPUT_JSON = "olx_car_cover_results.json"
OUTPUT_CSV = "olx_car_cover_results.csv"


def safe_get(url: str, session: requests.Session, timeout: int = 15) -> Optional[requests.Response]:
    try:
        resp = session.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"[WARN] Failed to GET {url}: {e}", file=sys.stderr)
        return None


def find_listing_links_from_search(html: str, base_url: str) -> List[str]:
    """
    Extract candidate listing URLs from a search-results page HTML.
    We look for anchors pointing to an OLX item (heuristic: '/item/' or '/p/' or '/view/').
    """
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    urls = set()
    for a in anchors:
        href = a["href"].strip()
        # Normalize relative urls
        if href.startswith("/"):
            href = urljoin(base_url, href)
        # Heuristic: OLX item pages often contain '/item/' or '/p/' or '/view/'
        if re.search(r"/item/|/p/|/view/|/i/", href):
            parsed = urlparse(href)
            # ignore links to other domains
            if parsed.netloc and "olx" in parsed.netloc:
                # keep only http(s)
                if parsed.scheme in ("http", "https"):
                    urls.add(href.split("?")[0].rstrip("/"))
    return list(urls)


def extract_listing_summary_from_card(card) -> Dict:
    """
    Try to extract title/price/location from a result 'card' or anchor tag.
    This is a fallback; the main robust approach is to follow a listing and parse its page.
    """
    title = None
    price = None
    location = None
    snippet = None
    url = None

    # If card is an anchor tag or contains an anchor
    a = card.find("a", href=True)
    if a:
        url = a["href"]
        title = a.get_text(strip=True) or None

    # try to find common price patterns
    price_tag = card.find(lambda t: t.name in ("span", "p", "div") and re.search(r"₹|\bINR\b|\brs\b", t.get_text("", strip=True), re.I))
    if price_tag:
        price = price_tag.get_text(" ", strip=True)

    # location often in small tags or divs containing city names
    loc_tag = card.find(lambda t: t.name in ("span", "p", "div") and "location" in (t.get("class") or []) )
    if not loc_tag:
        # fallback: look for any small text with a comma (City, State)
        candidates = card.find_all(["span", "p", "div"])
        for c in candidates[-4:]:
            txt = c.get_text(" ", strip=True)
            if txt and re.search(r"[A-Za-z].+[,]\s*[A-Za-z]", txt):
                location = txt
                break
    else:
        location = loc_tag.get_text(" ", strip=True)

    # snippet or short description
    desc_tag = card.find("p")
    if desc_tag:
        snippet = desc_tag.get_text(" ", strip=True)

    return {"title": title, "url": url, "price": price, "location": location, "snippet": snippet}


def parse_listing_page(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    data = {"title": None, "price": None, "location": None, "description": None, "images": []}

    # Title
    title_tag = soup.find(["h1", "h2"])
    if title_tag:
        data["title"] = title_tag.get_text(" ", strip=True)

    # Price
    # Try common OLX patterns
    price_tag = soup.find(lambda t: t.name in ("span", "div") and re.search(r"₹|INR|rs\.", t.get_text("", strip=True), re.I))
    if price_tag:
        data["price"] = price_tag.get_text(" ", strip=True)

    # Description - often in <section> or <div> with long text
    desc_candidates = soup.find_all(["div", "section", "p"])
    longest = ""
    for c in desc_candidates:
        txt = c.get_text(" ", strip=True)
        if len(txt) > len(longest):
            longest = txt
    if longest:
        data["description"] = longest.strip()

    # Images - look for img tags
    imgs = soup.find_all("img", src=True)
    for img in imgs:
        src = img.get("src")
        if src and not src.startswith("data:"):
            data["images"].append(urljoin(url, src))

    return data


def scrape_search(url: str, pages: int = 1, visit_details: bool = False, use_selenium: bool = False) -> List[Dict]:
    """
    Main scrape routine. pages=number of search result pages to attempt.
    visit_details: if True, fetch each listing page and parse more fields.
    use_selenium: if True, stub for a Selenium-based flow (not implemented here).
    """
    session = requests.Session()
    results = []
    seen = set()

    for p in range(1, pages + 1):
        page_url = url
        if p > 1:
            # common pagination parameter may be '?page=N' or '/?page=N'
            join_char = "&" if "?" in url else "?"
            page_url = f"{url}{join_char}page={p}"

        print(f"[INFO] Fetching search page: {page_url}")
        resp = safe_get(page_url, session)
        if not resp:
            continue

        candidates = find_listing_links_from_search(resp.text, base_url=url)
        print(f"[INFO] Found {len(candidates)} candidate listing URLs on page {p}.")

        for item_url in candidates:
            if item_url in seen:
                continue
            seen.add(item_url)
            item = {"url": item_url}

            if visit_details:
                print(f"[INFO] Visiting {item_url}")
                time.sleep(1.0)  # polite delay
                r = safe_get(item_url, session)
                if r and r.text:
                    parsed = parse_listing_page(r.text, item_url)
                    item.update(parsed)
                else:
                    print(f"[WARN] Could not fetch details for {item_url}")
            else:
                # Try to extract summary info from the search page by finding the anchor again
                soup = BeautifulSoup(resp.text, "html.parser")
                # find the anchor element and try to get surrounding card
                a = soup.find("a", href=True, attrs={"href": re.compile(re.escape(item_url))})
                if a:
                    card = a.find_parent()
                    summary = extract_listing_summary_from_card(card if card else a)
                    item.update(summary)
                else:
                    item.update({"title": None, "price": None, "location": None, "description": None, "images": []})

            results.append(item)

    return results


def save_results(results: List[Dict], json_path: str = OUTPUT_JSON, csv_path: str = OUTPUT_CSV):
    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Saved JSON -> {json_path}")

    # CSV - flatten keys conservatively
    keys = ["title", "url", "price", "location", "description", "images", "snippet"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in results:
            row = {k: (json.dumps(r.get(k)) if isinstance(r.get(k), (list, dict)) else (r.get(k) or "")) for k in keys}
            writer.writerow(row)
    print(f"[INFO] Saved CSV -> {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Scrape OLX search results for car covers and save to files.")
    parser.add_argument("--url", required=True, help="OLX search URL (example: https://www.olx.in/items/q-car-cover)")
    parser.add_argument("--pages", type=int, default=1, help="Number of search result pages to attempt")
    parser.add_argument("--visit-details", action="store_true", help="Visit each listing page to collect more details (slower)")
    parser.add_argument("--use-selenium", action="store_true", help="Use Selenium for JS-heavy pages (not implemented automatically)")
    args = parser.parse_args()

    results = scrape_search(args.url, pages=args.pages, visit_details=args.visit_details, use_selenium=args.use_selenium)
    save_results(results)


if __name__ == "__main__":
    main()
