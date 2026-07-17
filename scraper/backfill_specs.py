"""One-off: re-run spec extraction over stored titles (after parser fixes) and re-export."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import db, parse

con = db.connect()
n = 0
for row in con.execute("SELECT asin, title FROM products WHERE title IS NOT NULL").fetchall():
    specs = parse.extract_specs(row["title"])
    con.execute("UPDATE products SET specs=?, brand=?, model_line=? WHERE asin=?",
                (json.dumps(specs), specs.get("brand"), specs.get("model_line"), row["asin"]))
    n += 1
con.commit()
print(f"re-extracted specs for {n} products, exported {db.export_json(con)}")
con.close()
