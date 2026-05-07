#!/usr/bin/env python3
"""
Populate sets.image_url from TCGPlayer's product image CDN.

Uses the ETB product image for each set; falls back to Booster Box,
then Booster Pack. Skips sets that already have an image_url.
"""
import sqlite3
from typing import Optional

DB_PATH = "pokemon_prices.db"
CDN = "https://product-images.tcgplayer.com/fit-in/400x550/{product_id}.jpg"
PRIORITY = ["Elite Trainer Box", "Booster Box", "Booster Pack"]


def pick_product_id(conn, group_id: int) -> Optional[int]:
    for product_type in PRIORITY:
        row = conn.execute(
            "SELECT product_id FROM products WHERE group_id = ? AND product_type = ?",
            (group_id, product_type),
        ).fetchone()
        if row:
            return row["product_id"]
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sets = conn.execute(
        "SELECT group_id, name FROM sets WHERE image_url IS NULL ORDER BY published_on"
    ).fetchall()

    if not sets:
        print("All sets already have image URLs.")
        conn.close()
        return

    updated = 0
    skipped = 0
    for s in sets:
        pid = pick_product_id(conn, s["group_id"])
        if pid is None:
            print(f"  SKIP  {s['name']} — no matching product found")
            skipped += 1
            continue

        url = CDN.format(product_id=pid)
        conn.execute(
            "UPDATE sets SET image_url = ? WHERE group_id = ?",
            (url, s["group_id"]),
        )
        print(f"  SET   {s['name']} → product {pid}")
        updated += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
