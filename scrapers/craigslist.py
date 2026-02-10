"""Craigslist apartment listing scraper."""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

# Craigslist neighborhood search terms mapped to our canonical names
CL_NEIGHBORHOOD_TERMS = {
    "Gowanus": "gowanus",
    "Fort Greene": "fort greene",
    "Carroll Gardens": "carroll gardens",
    "Greenpoint": "greenpoint",
    "Bed-Stuy": "bed-stuy",
    "Clinton Hill": "clinton hill",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class CraigslistScraper:
    """Scrapes apartment listings from Craigslist New York (Brooklyn)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def build_search_url(self, neighborhood_term=None):
        """Build a Craigslist search URL with filters."""
        params = {
            "min_price": 0,
            "max_price": config.MAX_PRICE,
            "min_bedrooms": config.MIN_BEDROOMS,
            "max_bedrooms": config.MAX_BEDROOMS,
            "availabilityMode": 0,
        }
        if neighborhood_term:
            params["query"] = neighborhood_term

        base = config.CRAIGSLIST_BASE_URL + config.CRAIGSLIST_SEARCH_PATH
        return f"{base}?{urlencode(params)}"

    def _generate_id(self, url):
        """Generate a stable ID from a listing URL."""
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def _match_neighborhood(self, title, body_text=""):
        """Try to identify which target neighborhood a listing belongs to."""
        combined = f"{title} {body_text}".lower()
        for name, term in CL_NEIGHBORHOOD_TERMS.items():
            if term in combined:
                return name
        return None

    def scrape(self):
        """Fetch and parse Craigslist listings for all target neighborhoods."""
        all_listings = []

        for hood_name, hood_term in CL_NEIGHBORHOOD_TERMS.items():
            try:
                listings = self._scrape_neighborhood(hood_name, hood_term)
                all_listings.extend(listings)
                time.sleep(2)  # Be polite between requests
            except Exception:
                logger.exception("Error scraping Craigslist for %s", hood_name)

        logger.info("Craigslist: found %d total listings", len(all_listings))
        return all_listings

    def _scrape_neighborhood(self, hood_name, hood_term):
        """Scrape listings for a single neighborhood."""
        url = self.build_search_url(hood_term)
        logger.info("Scraping Craigslist: %s", url)

        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to fetch %s", url)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        listings = []

        # Craigslist uses <li class="cl-static-search-result"> for results
        results = soup.select("li.cl-static-search-result")
        if not results:
            # Fallback: try older markup
            results = soup.select(".result-row")

        for item in results:
            listing = self._parse_result(item, hood_name)
            if listing:
                listings.append(listing)

        # Also try the gallery/list view items
        if not listings:
            results = soup.select(".cl-search-result")
            for item in results:
                listing = self._parse_result_v2(item, hood_name)
                if listing:
                    listings.append(listing)

        return listings

    def _parse_result(self, item, default_neighborhood):
        """Parse a single Craigslist search result element."""
        link = item.select_one("a")
        if not link:
            return None

        url = link.get("href", "")
        if url and not url.startswith("http"):
            url = urljoin(config.CRAIGSLIST_BASE_URL, url)

        title = link.get_text(strip=True)
        if not title:
            return None

        # Extract price
        price = self._extract_price(item.get_text())

        # Extract metadata
        meta_text = item.get_text(" ", strip=True)
        bedrooms = self._extract_bedrooms(meta_text)
        neighborhood = self._match_neighborhood(title, meta_text) or default_neighborhood

        return {
            "id": self._generate_id(url),
            "source": "craigslist",
            "title": title,
            "url": url,
            "price": price,
            "bedrooms": bedrooms,
            "neighborhood": neighborhood,
            "image_url": self._extract_image(item),
            "date_posted": datetime.now(timezone.utc).isoformat(),
            "date_scraped": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_result_v2(self, item, default_neighborhood):
        """Parse newer Craigslist markup."""
        link = item.select_one("a.titlestring, a.posting-title, a")
        if not link:
            return None

        url = link.get("href", "")
        if url and not url.startswith("http"):
            url = urljoin(config.CRAIGSLIST_BASE_URL, url)

        title = link.get_text(strip=True)
        if not title:
            title_el = item.select_one(".title, .titlestring, .label")
            title = title_el.get_text(strip=True) if title_el else "Untitled"

        price = self._extract_price(item.get_text())
        meta_text = item.get_text(" ", strip=True)
        bedrooms = self._extract_bedrooms(meta_text)
        neighborhood = self._match_neighborhood(title, meta_text) or default_neighborhood

        return {
            "id": self._generate_id(url),
            "source": "craigslist",
            "title": title,
            "url": url,
            "price": price,
            "bedrooms": bedrooms,
            "neighborhood": neighborhood,
            "image_url": self._extract_image(item),
            "date_posted": datetime.now(timezone.utc).isoformat(),
            "date_scraped": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_price(self, text):
        """Extract price from text like '$2,500'."""
        match = re.search(r"\$[\d,]+", text)
        if match:
            return int(match.group().replace("$", "").replace(",", ""))
        return None

    def _extract_bedrooms(self, text):
        """Extract bedroom count from text."""
        match = re.search(r"(\d+)\s*br\b", text.lower())
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)\s*bed", text.lower())
        if match:
            return int(match.group(1))
        return None

    def _extract_image(self, item):
        """Extract thumbnail image URL if present."""
        img = item.select_one("img")
        if img:
            return img.get("src") or img.get("data-src")
        return None
