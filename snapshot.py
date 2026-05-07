#!/usr/bin/env python3
import sqlite3
import requests
import time
from collections import defaultdict
from datetime import date

DB_PATH = "pokemon_prices.db"
BASE_URL = "https://tcgcsv.com/tcgplayer/3"

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
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)

    # Load all products grouped by group_id, with set name for display
    rows = conn.execute("""
        SELECT p.product_id, p.group_id, s.name AS set_name
        FROM products p
        JOIN sets s ON p.group_id = s.group_id
    """).fetchall()

    # Find product_ids that already have a snapshot for today
    existing = {
        r[0] for r in conn.execute(
            "SELECT product_id FROM price_snapshots WHERE captured_at = ?", (today,)
        )
    }

    # Group by (group_id, set_name)
    groups = defaultdict(list)
    for product_id, group_id, set_name in rows:
        groups[(group_id, set_name)].append(product_id)

    total_snapshotted = 0
    total_skipped = 0

    for (group_id, set_name), product_ids in groups.items():
        to_snapshot = [pid for pid in product_ids if pid not in existing]
        skipped = len(product_ids) - len(to_snapshot)
        total_skipped += skipped

        if not to_snapshot:
            print(f"Snapshotting set: {set_name}... skipped (all {skipped} already done today)")
            continue

        print(f"Snapshotting set: {set_name}...", end=" ", flush=True)

        price_data = fetch_json(f"{BASE_URL}/{group_id}/prices")
        price_index = build_price_index(extract_results(price_data))

        inserted = 0
        for pid in to_snapshot:
            if pid not in price_index:
                total_skipped += 1
                continue
            pr = price_index[pid]
            conn.execute(
                "INSERT INTO price_snapshots "
                "(product_id, captured_at, low_price, mid_price, high_price, market_price) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, today,
                 pr.get("lowPrice"), pr.get("midPrice"),
                 pr.get("highPrice"), pr.get("marketPrice")),
            )
            inserted += 1

        conn.commit()
        total_snapshotted += inserted
        print(f"done ({inserted} products)")
        time.sleep(0.4)

    conn.close()
    print(f"\nSummary: {total_snapshotted} snapshotted, {total_skipped} skipped.")


if __name__ == "__main__":
    main()
