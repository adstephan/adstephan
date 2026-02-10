"""Script to fetch new listings from all sources."""

import logging
import sys

import database
from scrapers import CraigslistScraper, StreetEasyScraper, ZillowScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def update_all():
    """Run all scrapers and update the database."""
    database.init_db()

    scrapers = [
        ("craigslist", CraigslistScraper()),
        ("streeteasy", StreetEasyScraper()),
        ("zillow", ZillowScraper()),
    ]

    total_new = 0

    for name, scraper in scrapers:
        logger.info("Running %s scraper...", name)
        try:
            listings = scraper.scrape()
            new_count = database.upsert_listings(listings)
            database.log_scrape(name, len(listings), "success")
            logger.info(
                "%s: %d listings found, %d new", name, len(listings), new_count
            )
            total_new += new_count
        except Exception as e:
            logger.exception("Error running %s scraper", name)
            database.log_scrape(name, 0, "error", str(e))

    logger.info("Update complete. %d new listings added.", total_new)
    return total_new


if __name__ == "__main__":
    update_all()
