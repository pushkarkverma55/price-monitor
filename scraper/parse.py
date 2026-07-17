"""HTML parsing + spec extraction for Amazon.in pages."""
import html as htmllib
import json
import re

BLOCK_MARKERS = ("api-services-support@amazon.com", "Robot Check", "Enter the characters you see below")


def is_blocked(page_html):
    return len(page_html) < 20000 or any(m in page_html for m in BLOCK_MARKERS)


def parse_search(page_html):
    """Return ordered unique ASINs from a search results page (organic results only)."""
    asins = []
    # each result card: <div data-asin="..." data-component-type="s-search-result">
    for m in re.finditer(r'data-asin="([A-Z0-9]{10})"[^>]*data-component-type="s-search-result"', page_html):
        a = m.group(1)
        if a not in asins:
            asins.append(a)
    if not asins:  # attribute order can flip
        for m in re.finditer(r'data-component-type="s-search-result"[^>]*data-asin="([A-Z0-9]{10})"', page_html):
            a = m.group(1)
            if a not in asins:
                asins.append(a)
    return asins


def _to_int(s):
    try:
        return int(re.sub(r"[^\d]", "", s))
    except (ValueError, TypeError):
        return None


def parse_product(page_html):
    """Extract title, price, mrp, rating, ratings_count, availability, parent_asin, variants."""
    out = {}
    m = re.search(r'id="productTitle"[^>]*>\s*(.*?)\s*</span>', page_html, re.S)
    out["title"] = htmllib.unescape(m.group(1)).strip() if m else None

    # buybox price: first a-price-whole inside core price block; fall back to first on page
    core = re.search(r'id="corePriceDisplay[^"]*"(.{0,4000}?)</div>', page_html, re.S)
    hay = core.group(1) if core else page_html
    m = re.search(r'class="a-price-whole">([\d,]+)', hay)
    out["price"] = _to_int(m.group(1)) if m else None

    m = re.search(r'class="a-price a-text-price"[^>]*>\s*<span[^>]*>\s*(?:&#8377;|₹)?\s*([\d,]+)', page_html)
    out["mrp"] = _to_int(m.group(1)) if m else None

    m = re.search(r'([\d.]+) out of 5 stars', page_html)
    out["rating"] = float(m.group(1)) if m else None

    m = re.search(r'id="acrCustomerReviewText"[^>]*>\s*\(?([\d,]+)', page_html)
    out["ratings_count"] = _to_int(m.group(1)) if m else None

    m = re.search(r'id="availability"[^>]*>.*?<span[^>]*>\s*(.*?)\s*<', page_html, re.S)
    out["availability"] = htmllib.unescape(m.group(1)).strip() if m else None
    if out["availability"] is None and out["price"] is not None:
        out["availability"] = "In stock"

    m = re.search(r'"parentAsin"\s*:\s*"([A-Z0-9]{10})"', page_html)
    out["parent_asin"] = m.group(1) if m else None

    out["variants"] = {}
    m = re.search(r'"dimensionValuesDisplayData"\s*:\s*(\{.*?\})\s*,\s*"', page_html, re.S)
    if m:
        try:
            out["variants"] = {a: v for a, v in json.loads(m.group(1)).items()}
        except json.JSONDecodeError:
            pass
    return out


# ---- spec extraction from titles ----

CPU_PATTERNS = [
    (r'\b(?:Intel\s+)?Core\s+Ultra\s+([579])\b[\s-]*(\w{3,10})?', lambda m: (f"Core Ultra {m.group(1)}", "intel")),
    (r'\b(?:Intel\s+Core\s+|Core\s+)?i([3579])[\s-]?(\d{4,5}[A-Z]{0,2})\b', lambda m: (f"i{m.group(1)}-{m.group(2)}", "intel")),
    (r'\b(?:Intel\s+Core\s+|Core\s+)i([3579])\b', lambda m: (f"i{m.group(1)}", "intel")),
    (r'\bRyzen\s*([3579])\s+(\d{4}[A-Z]{0,3})\b', lambda m: (f"Ryzen {m.group(1)} {m.group(2)}", "amd")),
    (r'\bR([3579])[\s-]?(\d{4}[A-Z]{0,3})\b', lambda m: (f"Ryzen {m.group(1)} {m.group(2)}", "amd")),
    (r'\bRyzen\s*([3579])\b', lambda m: (f"Ryzen {m.group(1)}", "amd")),
    (r'\bSnapdragon\s+(X\s*\w+)', lambda m: (f"Snapdragon {m.group(1)}", "qualcomm")),
    (r'\b(Celeron|Pentium|Athlon)\b', lambda m: (m.group(1), "entry")),
    (r'\bM([1234])\b(?:\s+(Pro|Max))?', lambda m: (f"M{m.group(1)}" + (f" {m.group(2)}" if m.group(2) else ""), "apple")),
]

KNOWN_BRANDS = ["Lenovo", "HP", "Dell", "ASUS", "Acer", "MSI", "Apple", "Samsung", "Infinix", "Honor", "Microsoft", "LG", "Gigabyte", "Colorful", "Chuwi", "Ultimus", "Zebronics", "Primebook", "Wings", "Walker", "Thomson", "Realme", "Xiaomi", "Redmi"]


def extract_specs(title):
    """brand, model_line, ram_gb, storage, cpu, cpu_family from an Amazon.in laptop title."""
    if not title:
        return {}
    t = " ".join(title.split())
    specs = {}

    brand = None
    for b in KNOWN_BRANDS:
        if re.search(rf'\b{re.escape(b)}\b', t, re.I):
            brand = b
            break
    specs["brand"] = brand or t.split()[0]

    # explicit "16GB RAM" wins; else first NGB not tied to storage/GPU VRAM
    m = re.search(r'\b(\d{1,2})\s*GB\b(?:\s+(?:DDR\d\w*|LPDDR\d\w*))?\s+RAM\b', t, re.I)
    if not m:
        m = re.search(r'\b(\d{1,2})\s*GB\b(?!\s*(?:SSD|HDD|eMMC|Storage|Graphics|GDDR|VRAM|RTX|GTX|GPU))', t, re.I)
    specs["ram_gb"] = int(m.group(1)) if m else None

    # storage needs an explicit storage word; fallback: slash-delimited "…/512GB" that isn't the RAM
    m = re.search(r'\b(\d+)\s*(TB|GB)\s*(?:PCIe\s+)?(?:NVMe\s+)?(?:Gen\d\s+)?(?:SSD|HDD|eMMC|UFS|Storage)\b', t, re.I)
    storage = f"{m.group(1)}{m.group(2).upper()}" if m else None
    if storage is None:
        for m2 in re.finditer(r'/\s*(\d+)\s*(TB|GB)\b(?!\s*(?:Graphics|GDDR|VRAM))', t, re.I):
            n, unit = int(m2.group(1)), m2.group(2).upper()
            if unit == "TB" or n >= 128:  # laptop storage, not RAM/VRAM sizes
                storage = f"{n}{unit}"
                break
    specs["storage"] = storage
    specs["storage_gb"] = (int(storage[:-2]) * (1024 if storage.endswith("TB") else 1)) if storage else None

    specs["cpu"], specs["cpu_family"] = None, None
    for pat, fmt in CPU_PATTERNS:
        m = re.search(pat, t, re.I)
        if m:
            specs["cpu"], specs["cpu_family"] = fmt(m)
            break

    # model line: words after brand, stopping at spec/CPU/punctuation tokens
    model = None
    if brand:
        after = re.split(rf'\b{re.escape(brand)}\b', t, maxsplit=1, flags=re.I)[-1].strip()
        after = re.sub(r'^(Smartchoice|Smart\s*Choice|New|Latest)\s+', '', after, flags=re.I)
        words = []
        stop = re.compile(r'^(\(|\[|\d+GB|\d+TB|\d+(st|nd|rd|th)\b|Intel|AMD|Ryzen|Core\b|i[3579]\b|R[3579]\b|Snapdragon|Qualcomm|Celeron|MediaTek|with\b|Laptop\b|Thin\b|,)', re.I)
        for w in after.split():
            if stop.match(w):
                break
            words.append(w)
            if len(words) >= 4:
                break
        model = " ".join(words).strip(" ,-|") or None
    specs["model_line"] = model
    return specs
