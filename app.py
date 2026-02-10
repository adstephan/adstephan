"""Flask application for the apartment finder dashboard."""

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request

import config
import database
from scrapers.streeteasy import StreetEasyScraper
from scrapers.zillow import ZillowScraper
from update_listings import update_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# --- Routes ---


@app.route("/")
def index():
    """Serve the main dashboard page."""
    streeteasy_urls = StreetEasyScraper.get_all_search_urls()
    zillow_urls = ZillowScraper.get_all_search_urls()
    return render_template(
        "index.html",
        neighborhoods=config.NEIGHBORHOODS,
        max_price=config.MAX_PRICE,
        min_bedrooms=config.MIN_BEDROOMS,
        max_bedrooms=config.MAX_BEDROOMS,
        streeteasy_urls=streeteasy_urls,
        zillow_urls=zillow_urls,
    )


@app.route("/api/listings")
def api_listings():
    """Return listings as JSON with optional filters."""
    source = request.args.get("source")
    neighborhood = request.args.get("neighborhood")
    min_price = request.args.get("min_price", type=int)
    max_price = request.args.get("max_price", type=int)
    bedrooms = request.args.get("bedrooms", type=int)
    sort_by = request.args.get("sort_by", "date_scraped")
    sort_order = request.args.get("sort_order", "desc")

    listings = database.get_listings(
        source=source,
        neighborhood=neighborhood,
        min_price=min_price,
        max_price=max_price,
        bedrooms=bedrooms,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return jsonify(listings)


@app.route("/api/stats")
def api_stats():
    """Return summary statistics."""
    return jsonify(database.get_stats())


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Trigger a manual refresh of listings."""
    thread = threading.Thread(target=update_all, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "Refresh started in background"})


@app.route("/api/search-links")
def api_search_links():
    """Return direct search links for all sources and neighborhoods."""
    return jsonify(
        {
            "streeteasy": StreetEasyScraper.get_all_search_urls(),
            "zillow": ZillowScraper.get_all_search_urls(),
            "craigslist": {
                name: (
                    f"{config.CRAIGSLIST_BASE_URL}{config.CRAIGSLIST_SEARCH_PATH}"
                    f"?query={name.lower().replace(' ', '+')}"
                    f"&min_price=0&max_price={config.MAX_PRICE}"
                    f"&min_bedrooms={config.MIN_BEDROOMS}"
                    f"&max_bedrooms={config.MAX_BEDROOMS}"
                )
                for name in config.NEIGHBORHOODS
            },
        }
    )


# --- Startup ---


def start_scheduler():
    """Start the background scheduler for periodic updates."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        update_all,
        "interval",
        minutes=config.UPDATE_INTERVAL_MINUTES,
        id="update_listings",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — updating every %d minutes",
        config.UPDATE_INTERVAL_MINUTES,
    )


if __name__ == "__main__":
    database.init_db()

    # Run initial scrape in background
    logger.info("Running initial listing fetch...")
    threading.Thread(target=update_all, daemon=True).start()

    # Start periodic scheduler
    start_scheduler()

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
    )
