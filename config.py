"""Configuration for the apartment finder application."""

# Search criteria
MAX_PRICE = 4000
MIN_BEDROOMS = 1
MAX_BEDROOMS = 2

NEIGHBORHOODS = [
    "Gowanus",
    "Fort Greene",
    "Carroll Gardens",
    "Greenpoint",
    "Bed-Stuy",
    "Clinton Hill",
]

# Craigslist configuration
CRAIGSLIST_BASE_URL = "https://newyork.craigslist.org"
CRAIGSLIST_SEARCH_PATH = "/search/brk/apa"

# StreetEasy neighborhood slugs
STREETEASY_NEIGHBORHOODS = {
    "Gowanus": "gowanus",
    "Fort Greene": "fort-greene",
    "Carroll Gardens": "carroll-gardens",
    "Greenpoint": "greenpoint",
    "Bed-Stuy": "bed-stuy",
    "Clinton Hill": "clinton-hill",
}

# Zillow neighborhood slugs
ZILLOW_NEIGHBORHOODS = {
    "Gowanus": "gowanus-brooklyn-new-york-ny",
    "Fort Greene": "fort-greene-brooklyn-new-york-ny",
    "Carroll Gardens": "carroll-gardens-brooklyn-new-york-ny",
    "Greenpoint": "greenpoint-brooklyn-new-york-ny",
    "Bed-Stuy": "bedford-stuyvesant-brooklyn-new-york-ny",
    "Clinton Hill": "clinton-hill-brooklyn-new-york-ny",
}

# Update interval in minutes
UPDATE_INTERVAL_MINUTES = 30

# Database
DATABASE_PATH = "listings.db"

# Flask
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8080
