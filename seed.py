#!/usr/bin/env python3
import sqlite3
import requests
import time
from datetime import datetime, timezone

DB_PATH = "pokemon_prices.db"
BASE_URL = "https://tcgcsv.com/tcgplayer/3"

SETS_BY_ERA = {
    "Sword & Shield": [
        "SSH", "RCL", "DAA", "CPA", "VIV", "SHF", "BST", "CRE", "EVS",
        "CEL", "FST", "BRS", "ASR", "PGO", "LOR", "SIT", "CRZ",
    ],
    "Scarlet & Violet": [
        "SVI", "PAL", "OBF", "MEW", "PAR", "PAF", "TEF", "TWM", "SFA",
        "SCR", "SSP", "PRE", "JTG", "DRI", "BLK", "WHT",
    ],
    "Mega Evolution": ["MEG", "PFL", "ASC", "POR"],
}

SEALED_KEYWORDS = ["Booster Box", "Pokemon Center Elite Trainer Box", "Elite Trainer Box", "Booster Pack"]
EXCLUDE_KEYWORDS = ["Case", "Bundle", "Sleeved", "Code Card", "Half Booster", "Set of"]

TOTAL_SETS = sum(len(v) for v in SETS_BY_ERA.values())

# tcgcsv uses TCGPlayer abbreviations which differ from standard Pokémon TCG ones.
# Keys are our canonical abbreviations; values are what the API returns.
ABBREV_ALIAS = {
    "SSH": "SWSH01",
    "RCL": "SWSH02",
    "DAA": "SWSH03",
    "CPA": "CHP",
    "VIV": "SWSH04",
    "BST": "SWSH05",
    "CRE": "SWSH06",
    "EVS": "SWSH07",
    "CEL": "CLB",
    "FST": "SWSH08",
    "BRS": "SWSH09",
    "ASR": "SWSH10",
    "LOR": "SWSH11",
    "SIT": "SWSH12",
}


def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sets (
            group_id     INTEGER PRIMARY KEY,
            name         TEXT NOT NULL,
            abbreviation TEXT NOT NULL,
            era          TEXT NOT NULL,
            published_on TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id   INTEGER PRIMARY KEY,
            group_id     INTEGER NOT NULL REFERENCES sets(group_id),
            name         TEXT NOT NULL,
            product_type TEXT,
            image_url    TEXT,
            url          TEXT
        );

        CREATE TABLE IF NOT EXISTS price_snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER NOT NULL REFERENCES products(product_id),
            captured_at  TEXT NOT NULL,
            low_price    REAL,
            mid_price    REAL,
            high_price   REAL,
            market_price REAL
        );
    """)
    conn.commit()


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_json(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_results(data):
    if isinstance(data, dict):
        return data.get("results", [])
    if isinstance(data, list):
        return data
    return []


def build_price_index(prices_raw):
    """One price row per productId, preferring Normal/no subtype."""
    index = {}
    for row in prices_raw:
        pid = row.get("productId")
        if pid is None:
            continue
        subtype = (row.get("subTypeName") or "").strip()
        if pid not in index or subtype in ("", "Normal"):
            index[pid] = row
    return index


def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    print(f"Database ready: {DB_PATH}")
    print(f"Targeting {TOTAL_SETS} sets across {len(SETS_BY_ERA)} eras.\n")

    abbrev_to_era = {
        abbrev.upper(): era
        for era, abbrevs in SETS_BY_ERA.items()
        for abbrev in abbrevs
    }

    # Build reverse alias: API abbreviation -> our canonical abbreviation
    api_to_canonical = {v.upper(): k for k, v in ABBREV_ALIAS.items()}
    # Also map any abbreviation that needs no alias to itself
    for abbrev in abbrev_to_era:
        if abbrev not in ABBREV_ALIAS:
            api_to_canonical[abbrev] = abbrev

    print("Fetching groups from tcgcsv.com ...")
    all_groups = extract_results(fetch_json(f"{BASE_URL}/groups"))
    print(f"  API returned {len(all_groups)} total groups.")

    matched = []
    for g in all_groups:
        api_abbrev = g.get("abbreviation", "").upper()
        canonical = api_to_canonical.get(api_abbrev)
        if canonical and canonical in abbrev_to_era:
            matched.append({
                "group_id":     g["groupId"],
                "name":         g["name"],
                "abbreviation": canonical,
                "era":          abbrev_to_era[canonical],
                "published_on": g.get("publishedOn"),
            })

    unmatched = abbrev_to_era.keys() - {m["abbreviation"] for m in matched}
    print(f"  Matched {len(matched)}/{TOTAL_SETS} sets.")
    if unmatched:
        print(f"  WARNING — no group found for: {', '.join(sorted(unmatched))}")

    captured_at = datetime.now(timezone.utc).isoformat()
    total_products = 0
    total_snapshots = 0

    for idx, s in enumerate(matched, 1):
        gid = s["group_id"]
        print(f"\n[{idx}/{len(matched)}] {s['abbreviation']} — {s['name']} ({s['era']})")

        conn.execute(
            "INSERT OR REPLACE INTO sets (group_id, name, abbreviation, era, published_on) "
            "VALUES (?, ?, ?, ?, ?)",
            (gid, s["name"], s["abbreviation"], s["era"], s["published_on"]),
        )

        print(f"  Fetching products ...")
        all_products = extract_results(fetch_json(f"{BASE_URL}/{gid}/products"))

        sealed = [
            p for p in all_products
            if any(kw in (p.get("name") or "") for kw in SEALED_KEYWORDS)
            and not any(ex in (p.get("name") or "") for ex in EXCLUDE_KEYWORDS)
        ]
        print(f"  {len(sealed)} sealed products (of {len(all_products)} total).")

        if not sealed:
            conn.commit()
            time.sleep(0.4)
            continue

        print(f"  Fetching prices ...")
        price_index = build_price_index(extract_results(fetch_json(f"{BASE_URL}/{gid}/prices")))

        n_products = 0
        n_snapshots = 0

        for p in sealed:
            pid = p.get("productId")
            name = p.get("name", "")
            product_type = next(
                (kw for kw in SEALED_KEYWORDS if kw in name), ""
            )

            conn.execute(
                "INSERT OR REPLACE INTO products "
                "(product_id, group_id, name, product_type, image_url, url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, gid, name, product_type,
                 p.get("imageUrl", ""), p.get("url", "")),
            )
            n_products += 1

            if pid in price_index:
                pr = price_index[pid]
                conn.execute(
                    "INSERT INTO price_snapshots "
                    "(product_id, captured_at, low_price, mid_price, high_price, market_price) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (pid, captured_at,
                     pr.get("lowPrice"), pr.get("midPrice"),
                     pr.get("highPrice"), pr.get("marketPrice")),
                )
                n_snapshots += 1

        conn.commit()
        print(f"  Inserted {n_products} products, {n_snapshots} price snapshots.")
        total_products += n_products
        total_snapshots += n_snapshots

        time.sleep(0.4)

    conn.close()
    print(f"\nDone — {len(matched)} sets | {total_products} products | {total_snapshots} price snapshots.")


if __name__ == "__main__":
    main()
