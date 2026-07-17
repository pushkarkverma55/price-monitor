"""SQLite storage + JSON export for the dashboard."""
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "pricemonitor.db"
DOCS_DATA = ROOT / "docs" / "data"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    asin TEXT PRIMARY KEY,
    title TEXT,
    brand TEXT,
    model_line TEXT,
    specs TEXT,               -- json: {ram_gb, storage, cpu, cpu_family}
    parent_asin TEXT,         -- twister parent; groups variant siblings
    discovered_via TEXT,      -- 'search' | 'variant'
    first_seen INTEGER,
    last_seen INTEGER,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    ts INTEGER NOT NULL,
    price INTEGER,            -- rupees; NULL if unavailable
    mrp INTEGER,
    rating REAL,
    ratings_count INTEGER,
    availability TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_asin_ts ON snapshots(asin, ts);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started INTEGER,
    finished INTEGER,
    pages_fetched INTEGER,
    products_snapshotted INTEGER,
    new_products INTEGER,
    errors TEXT
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_product(con, asin, title=None, brand=None, model_line=None,
                   specs=None, parent_asin=None, discovered_via="search"):
    now = int(time.time())
    row = con.execute("SELECT asin FROM products WHERE asin=?", (asin,)).fetchone()
    if row:
        sets, vals = ["last_seen=?"], [now]
        for col, v in [("title", title), ("brand", brand), ("model_line", model_line),
                       ("specs", json.dumps(specs) if specs else None),
                       ("parent_asin", parent_asin)]:
            if v is not None:
                sets.append(f"{col}=?")
                vals.append(v)
        vals.append(asin)
        con.execute(f"UPDATE products SET {', '.join(sets)} WHERE asin=?", vals)
        return False
    con.execute(
        "INSERT INTO products (asin, title, brand, model_line, specs, parent_asin, discovered_via, first_seen, last_seen) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (asin, title, brand, model_line, json.dumps(specs) if specs else None,
         parent_asin, discovered_via, now, now))
    return True


def add_snapshot(con, asin, price, mrp, rating, ratings_count, availability):
    con.execute(
        "INSERT INTO snapshots (asin, ts, price, mrp, rating, ratings_count, availability) VALUES (?,?,?,?,?,?,?)",
        (asin, int(time.time()), price, mrp, rating, ratings_count, availability))


def record_run(con, started, pages, snapped, new, errors):
    con.execute(
        "INSERT INTO runs (started, finished, pages_fetched, products_snapshotted, new_products, errors) VALUES (?,?,?,?,?,?)",
        (started, int(time.time()), pages, snapped, new, json.dumps(errors)))


def export_json(con):
    """Write docs/data/{catalog,history,meta}.json for the static dashboard."""
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    products = []
    for p in con.execute("SELECT * FROM products WHERE active=1 ORDER BY brand, model_line, asin"):
        snaps = con.execute(
            "SELECT ts, price, mrp, rating, ratings_count, availability FROM snapshots "
            "WHERE asin=? ORDER BY ts", (p["asin"],)).fetchall()
        if not snaps:
            continue
        latest = snaps[-1]
        prices = [s["price"] for s in snaps if s["price"] is not None]
        # grouping = matching definition: same brand + model line are variant siblings;
        # fall back to twister parent (or own asin) when model line extraction failed
        group = (f"{p['brand']}|{p['model_line']}".lower()
                 if p["brand"] and p["model_line"] else (p["parent_asin"] or p["asin"]))
        products.append({
            "asin": p["asin"],
            "title": p["title"],
            "brand": p["brand"],
            "model_line": p["model_line"],
            "specs": json.loads(p["specs"]) if p["specs"] else {},
            "group": group,
            "url": f"https://www.amazon.in/dp/{p['asin']}",
            "price": latest["price"],
            "mrp": latest["mrp"],
            "prev_price": next((s["price"] for s in reversed(snaps[:-1]) if s["price"] is not None), None),
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "rating": latest["rating"],
            "ratings_count": latest["ratings_count"],
            "availability": latest["availability"],
            "first_seen": p["first_seen"],
        })
    history = {}
    for p in products:
        rows = con.execute("SELECT ts, price FROM snapshots WHERE asin=? AND price IS NOT NULL ORDER BY ts",
                           (p["asin"],)).fetchall()
        history[p["asin"]] = [[r["ts"], r["price"]] for r in rows]
    runs = [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 20")]

    (DOCS_DATA / "catalog.json").write_text(json.dumps(
        {"generated_at": int(time.time()), "products": products}, ensure_ascii=False))
    (DOCS_DATA / "history.json").write_text(json.dumps(history))
    (DOCS_DATA / "meta.json").write_text(json.dumps({"runs": runs}))
    return len(products)
