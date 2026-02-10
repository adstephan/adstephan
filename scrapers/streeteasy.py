"""StreetEasy apartment listing scraper and link generator."""

import hashlib
import logging
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

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


class StreetEasyScraper:
    """Fetches apartment listings from StreetEasy."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    @staticmethod
    def build_search_url(neighborhood_slug):
        """Build a StreetEasy search URL for a neighborhood."""
        price_filter = f"price:-{config.MAX_PRICE}"
        beds_filter = f"beds:{config.MIN_BEDROOMS}-{config.MAX_BEDROOMS}"
        return (
            f"https://streeteasy.com/for-rent/{neighborhood_slug}"
            f"?{price_filter}%7C{beds_filter}"
        )

    @staticmethod
    def get_all_search_urls():
        """Return search URLs for all target neighborhoods."""
        urls = {}
        for name, slug in config.STREETEASY_NEIGHBORHOODS.items():
            urls[name] = StreetEasyScraper.build_search_url(slug)
        return urls

    def _generate_id(self, url):
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def scrape(self):
        """Attempt to scrape StreetEasy listings for all neighborhoods."""
        all_listings = []
        backoff = 5  # initial backoff in seconds

        for i, (hood_name, hood_slug) in enumerate(config.STREETEASY_NEIGHBORHOODS.items()):
            try:
                listings = self._scrape_neighborhood(hood_name, hood_slug)
                if listings is None:
                    # Got blocked — increase backoff and wait before retrying others
                    backoff = min(backoff * 2, 120)
                    delay = backoff + random.uniform(0, backoff * 0.5)
                    logger.info("Backing off %.1fs after StreetEasy block...", delay)
                    time.sleep(delay)
                else:
                    all_listings.extend(listings)
                    backoff = 5  # reset on success
                if i < len(config.STREETEASY_NEIGHBORHOODS) - 1:
                    delay = random.uniform(5, 12)
                    logger.info("Waiting %.1fs before next StreetEasy request...", delay)
                    time.sleep(delay)
            except Exception:
                logger.exception("Error scraping StreetEasy for %s", hood_name)

        logger.info("StreetEasy: found %d total listings", len(all_listings))
        return all_listings

    def _scrape_neighborhood(self, hood_name, hood_slug):
        """Scrape listings for a single neighborhood. Returns None on block."""
        url = self.build_search_url(hood_slug)
        logger.info("Scraping StreetEasy: %s", url)

        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 403:
                logger.warning(
                    "StreetEasy returned 403 for %s — site may be blocking scrapers",
                    hood_name,
                )
                return None
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to fetch StreetEasy %s", url)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        listings = []

        # StreetEasy listing cards
        cards = soup.select(
            "[data-testid='search-result'], "
            ".searchCardList--listItem, "
            ".listingCard, "
            ".search-card"
        )

        for card in cards:
            listing = self._parse_card(card, hood_name)
            if listing:
                listings.append(listing)

        return listings

    def _parse_card(self, card, neighborhood):
        """Parse a StreetEasy listing card."""
        link = card.select_one("a[href*='/rental/'], a[href*='/building/'], a")
        if not link:
            return None

        url = link.get("href", "")
        if url and not url.startswith("http"):
            url = f"https://streeteasy.com{url}"

        title = ""
        title_el = card.select_one(
            "[data-testid='listing-title'], .listingCard-title, h3, .title"
        )
        if title_el:
            title = title_el.get_text(strip=True)
        elif link:
            title = link.get_text(strip=True)

        if not title:
            return None

        price = self._extract_price(card.get_text())
        bedrooms = self._extract_bedrooms(card.get_text())

        img = card.select_one("img")
        image_url = img.get("src") if img else None

        return {
            "id": self._generate_id(url),
            "source": "streeteasy",
            "title": title,
            "url": url,
            "price": price,
            "bedrooms": bedrooms,
            "neighborhood": neighborhood,
            "image_url": image_url,
            "date_posted": datetime.now(timezone.utc).isoformat(),
            "date_scraped": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_price(self, text):
        match = re.search(r"\$[\d,]+", text)
        if match:
            return int(match.group().replace("$", "").replace(",", ""))
        return None

    def _extract_bedrooms(self, text):
        match = re.search(r"(\d+)\s*(?:br|bed|BD)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # Check for "studio"
        if re.search(r"\bstudio\b", text, re.IGNORECASE):
            return 0
        return None
