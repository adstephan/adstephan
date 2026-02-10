"""Zillow apartment listing scraper and link generator."""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class ZillowScraper:
    """Fetches apartment listings from Zillow."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    @staticmethod
    def build_search_url(neighborhood_slug):
        """Build a Zillow rental search URL for a neighborhood."""
        return f"https://www.zillow.com/{neighborhood_slug}/rentals/"

    @staticmethod
    def get_all_search_urls():
        """Return search URLs for all target neighborhoods."""
        urls = {}
        for name, slug in config.ZILLOW_NEIGHBORHOODS.items():
            urls[name] = ZillowScraper.build_search_url(slug)
        return urls

    def _generate_id(self, url):
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def scrape(self):
        """Attempt to scrape Zillow listings for all neighborhoods."""
        all_listings = []

        for hood_name, hood_slug in config.ZILLOW_NEIGHBORHOODS.items():
            try:
                listings = self._scrape_neighborhood(hood_name, hood_slug)
                all_listings.extend(listings)
                time.sleep(3)
            except Exception:
                logger.exception("Error scraping Zillow for %s", hood_name)

        logger.info("Zillow: found %d total listings", len(all_listings))
        return all_listings

    def _scrape_neighborhood(self, hood_name, hood_slug):
        """Scrape listings for a single neighborhood."""
        url = self.build_search_url(hood_slug)
        logger.info("Scraping Zillow: %s", url)

        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 403:
                logger.warning(
                    "Zillow returned 403 for %s — site may be blocking scrapers",
                    hood_name,
                )
                return []
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to fetch Zillow %s", url)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        listings = []

        # Zillow embeds listing data in a script tag as JSON
        script_data = self._extract_json_data(soup)
        if script_data:
            listings = self._parse_json_listings(script_data, hood_name)
        else:
            # Fallback: parse HTML cards
            listings = self._parse_html_listings(soup, hood_name)

        return listings

    def _extract_json_data(self, soup):
        """Try to extract listing data from Zillow's embedded JSON."""
        for script in soup.select("script[type='application/json']"):
            text = script.string or ""
            if "listResults" in text or "searchResults" in text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue

        # Try __NEXT_DATA__
        next_data = soup.select_one("script#__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                return json.loads(next_data.string)
            except json.JSONDecodeError:
                pass

        return None

    def _parse_json_listings(self, data, hood_name):
        """Parse listings from Zillow's JSON data structure."""
        listings = []

        # Navigate the nested JSON to find listing results
        results = self._find_nested_key(data, "listResults") or []
        if not results:
            results = self._find_nested_key(data, "searchResults") or []

        for item in results:
            if not isinstance(item, dict):
                continue

            price = item.get("price") or item.get("unformattedPrice")
            if isinstance(price, str):
                price_match = re.search(r"[\d,]+", price.replace("$", ""))
                price = int(price_match.group().replace(",", "")) if price_match else None

            # Filter by budget
            if price and price > config.MAX_PRICE:
                continue

            bedrooms = item.get("beds")
            if bedrooms is not None:
                try:
                    bedrooms = int(bedrooms)
                except (ValueError, TypeError):
                    bedrooms = None

            url = item.get("detailUrl", "")
            if url and not url.startswith("http"):
                url = f"https://www.zillow.com{url}"

            if not url:
                continue

            listings.append(
                {
                    "id": self._generate_id(url),
                    "source": "zillow",
                    "title": item.get("address", item.get("statusText", "Zillow Listing")),
                    "url": url,
                    "price": price,
                    "bedrooms": bedrooms,
                    "neighborhood": hood_name,
                    "image_url": item.get("imgSrc"),
                    "date_posted": datetime.now(timezone.utc).isoformat(),
                    "date_scraped": datetime.now(timezone.utc).isoformat(),
                }
            )

        return listings

    def _parse_html_listings(self, soup, hood_name):
        """Fallback: parse listing cards from HTML."""
        listings = []

        cards = soup.select(
            "[data-test='property-card'], "
            ".list-card, "
            ".property-card, "
            "article.property-card"
        )

        for card in cards:
            link = card.select_one("a[href*='/homedetails/'], a[href*='/b/'], a")
            if not link:
                continue

            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://www.zillow.com{url}"

            title_el = card.select_one("address, .list-card-addr, [data-test='property-card-addr']")
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            price = self._extract_price(card.get_text())
            bedrooms = self._extract_bedrooms(card.get_text())

            if price and price > config.MAX_PRICE:
                continue

            img = card.select_one("img")
            image_url = img.get("src") if img else None

            listings.append(
                {
                    "id": self._generate_id(url),
                    "source": "zillow",
                    "title": title or "Zillow Listing",
                    "url": url,
                    "price": price,
                    "bedrooms": bedrooms,
                    "neighborhood": hood_name,
                    "image_url": image_url,
                    "date_posted": datetime.now(timezone.utc).isoformat(),
                    "date_scraped": datetime.now(timezone.utc).isoformat(),
                }
            )

        return listings

    def _find_nested_key(self, data, key):
        """Recursively find a key in nested dicts/lists."""
        if isinstance(data, dict):
            if key in data:
                return data[key]
            for v in data.values():
                result = self._find_nested_key(v, key)
                if result is not None:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_nested_key(item, key)
                if result is not None:
                    return result
        return None

    def _extract_price(self, text):
        match = re.search(r"\$[\d,]+", text)
        if match:
            return int(match.group().replace("$", "").replace(",", ""))
        return None

    def _extract_bedrooms(self, text):
        match = re.search(r"(\d+)\s*(?:br|bed|bd)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
