"""Orchestrator: seed from search, snapshot all tracked ASINs, discover variants, export.

Usage: python -m scraper.main [--no-search] [--limit N]
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import db, parse

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")


class Fetcher:
    def __init__(self, pw):
        self.browser = pw.chromium.launch(headless=True)
        self.ctx = self.browser.new_context(
            locale="en-IN", user_agent=UA, viewport={"width": 1440, "height": 900})
        self.page = self.ctx.new_page()
        self.pages_fetched = 0

    def get(self, url):
        """Fetch a URL politely; retry with backoff on block pages. Returns html or None."""
        for attempt in range(CONFIG["max_block_retries"] + 1):
            time.sleep(random.uniform(CONFIG["min_delay_s"], CONFIG["max_delay_s"]))
            try:
                self.page.goto(url, timeout=CONFIG["page_timeout_ms"], wait_until="domcontentloaded")
                self.page.wait_for_timeout(2500)
                html = self.page.content()
            except Exception as e:
                print(f"  fetch error {url}: {e}", flush=True)
                html = ""
            self.pages_fetched += 1
            if html and not parse.is_blocked(html):
                return html
            if attempt < CONFIG["max_block_retries"]:
                wait = CONFIG["block_backoff_s"] * (attempt + 1)
                print(f"  blocked on {url}, backing off {wait}s", flush=True)
                time.sleep(wait)
        return None

    def close(self):
        self.browser.close()


def run(do_search=True, limit=None):
    con = db.connect()
    started = int(time.time())
    errors = []
    new_products = 0
    snapped = 0

    with sync_playwright() as pw:
        f = Fetcher(pw)
        try:
            tracked = {r["asin"] for r in con.execute("SELECT asin FROM products WHERE active=1")}

            # 1) seed / refresh candidates from search
            if do_search and len(tracked) < CONFIG["max_products"]:
                for q in CONFIG["search_queries"]:
                    url = "https://www.amazon.in/s?k=" + q.replace(" ", "+")
                    html = f.get(url)
                    if html is None:
                        errors.append(f"search blocked: {q}")
                        continue
                    asins = parse.parse_search(html)[:CONFIG["max_search_results_per_query"]]
                    fresh = [a for a in asins if a not in tracked]
                    print(f"search '{q}': {len(asins)} results, {len(fresh)} new", flush=True)
                    for a in fresh:
                        if len(tracked) >= CONFIG["max_products"]:
                            break
                        if db.upsert_product(con, a, discovered_via="search"):
                            tracked.add(a)
                    con.commit()

            # 2) snapshot every tracked product; discover variant siblings as we go
            todo = [r["asin"] for r in con.execute(
                "SELECT asin FROM products WHERE active=1 ORDER BY last_seen ASC")]
            if limit:
                todo = todo[:limit]
            for i, asin in enumerate(todo):
                html = f.get(f"https://www.amazon.in/dp/{asin}")
                if html is None:
                    errors.append(f"product blocked: {asin}")
                    continue
                p = parse.parse_product(html)
                if not p["title"]:
                    errors.append(f"no title (page changed?): {asin}")
                    continue
                specs = parse.extract_specs(p["title"])
                if CONFIG["allowed_brands"] and specs.get("brand") not in CONFIG["allowed_brands"]:
                    con.execute("UPDATE products SET active=0 WHERE asin=?", (asin,))
                    con.commit()
                    print(f"[{i+1}/{len(todo)}] {asin} skipped (brand {specs.get('brand')})", flush=True)
                    continue
                db.upsert_product(con, asin, title=p["title"], brand=specs.get("brand"),
                                  model_line=specs.get("model_line"), specs=specs,
                                  parent_asin=p["parent_asin"])
                db.add_snapshot(con, asin, p["price"], p["mrp"], p["rating"],
                                p["ratings_count"], p["availability"])
                snapped += 1
                # variant siblings from twister
                for sib in p["variants"]:
                    if sib not in tracked and len(tracked) < CONFIG["max_products"]:
                        if db.upsert_product(con, sib, parent_asin=p["parent_asin"],
                                             discovered_via="variant"):
                            tracked.add(sib)
                            new_products += 1
                            todo.append(sib)
                con.commit()
                print(f"[{i+1}/{len(todo)}] {asin} ₹{p['price']} {specs.get('model_line')} "
                      f"{specs.get('ram_gb')}GB/{specs.get('storage')}/{specs.get('cpu')} "
                      f"+{len(p['variants'])} sibs", flush=True)
        finally:
            f.close()

    db.record_run(con, started, f.pages_fetched, snapped, new_products, errors)
    con.commit()
    n = db.export_json(con)
    con.close()
    print(f"done: {snapped} snapshotted, {new_products} new via variants, "
          f"{f.pages_fetched} pages, {len(errors)} errors, exported {n} products", flush=True)
    return len(errors) == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-search", action="store_true", help="skip search seeding, only snapshot known ASINs")
    ap.add_argument("--limit", type=int, default=None, help="snapshot at most N products (testing)")
    args = ap.parse_args()
    ok = run(do_search=not args.no_search, limit=args.limit)
    sys.exit(0 if ok else 1)
