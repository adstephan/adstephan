"""SQLite database for storing apartment listings."""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                price INTEGER,
                bedrooms INTEGER,
                neighborhood TEXT,
                image_url TEXT,
                date_posted TEXT,
                date_scraped TEXT,
                first_seen TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                listings_found INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                message TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_neighborhood ON listings(neighborhood)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active)"
        )
    logger.info("Database initialized")


def upsert_listings(listings):
    """Insert or update a batch of listings. Returns count of new listings."""
    new_count = 0
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        for listing in listings:
            cursor = conn.execute(
                "SELECT id FROM listings WHERE id = ? OR url = ?",
                (listing["id"], listing["url"]),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing listing
                conn.execute(
                    """
                    UPDATE listings
                    SET title = ?, price = ?, bedrooms = ?, neighborhood = ?,
                        image_url = ?, date_scraped = ?, is_active = 1
                    WHERE id = ? OR url = ?
                    """,
                    (
                        listing["title"],
                        listing.get("price"),
                        listing.get("bedrooms"),
                        listing.get("neighborhood"),
                        listing.get("image_url"),
                        now,
                        listing["id"],
                        listing["url"],
                    ),
                )
            else:
                # Insert new listing
                conn.execute(
                    """
                    INSERT INTO listings (id, source, title, url, price, bedrooms,
                        neighborhood, image_url, date_posted, date_scraped, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        listing["id"],
                        listing["source"],
                        listing["title"],
                        listing["url"],
                        listing.get("price"),
                        listing.get("bedrooms"),
                        listing.get("neighborhood"),
                        listing.get("image_url"),
                        listing.get("date_posted"),
                        now,
                        now,
                    ),
                )
                new_count += 1

    return new_count


def log_scrape(source, listings_found, status="success", message=None):
    """Log a scrape run."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO scrape_log (timestamp, source, listings_found, status, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                source,
                listings_found,
                status,
                message,
            ),
        )


def get_listings(source=None, neighborhood=None, min_price=None, max_price=None,
                 bedrooms=None, sort_by="date_scraped", sort_order="desc",
                 limit=200):
    """Retrieve listings with optional filters."""
    query = "SELECT * FROM listings WHERE is_active = 1"
    params = []

    if source:
        query += " AND source = ?"
        params.append(source)
    if neighborhood:
        query += " AND neighborhood = ?"
        params.append(neighborhood)
    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)
    if bedrooms is not None:
        query += " AND bedrooms = ?"
        params.append(bedrooms)

    allowed_sorts = {"date_scraped", "price", "first_seen", "neighborhood"}
    if sort_by not in allowed_sorts:
        sort_by = "date_scraped"

    order = "DESC" if sort_order == "desc" else "ASC"
    query += f" ORDER BY {sort_by} {order}"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_stats():
    """Get summary statistics about listings."""
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE is_active = 1"
        ).fetchone()[0]

        by_source = {}
        for row in conn.execute(
            "SELECT source, COUNT(*) as cnt FROM listings WHERE is_active = 1 GROUP BY source"
        ):
            by_source[row["source"]] = row["cnt"]

        by_neighborhood = {}
        for row in conn.execute(
            "SELECT neighborhood, COUNT(*) as cnt FROM listings WHERE is_active = 1 GROUP BY neighborhood"
        ):
            by_neighborhood[row["neighborhood"]] = row["cnt"]

        last_scrape = conn.execute(
            "SELECT MAX(timestamp) FROM scrape_log"
        ).fetchone()[0]

        return {
            "total_listings": total,
            "by_source": by_source,
            "by_neighborhood": by_neighborhood,
            "last_updated": last_scrape,
        }
