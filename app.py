#!/usr/bin/env python3
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

DB_PATH = "pokemon_prices.db"

app = FastAPI(title="Pokemon Price Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
def root():
    return FileResponse("index.html")


@app.get("/api/era/{era}")
def get_era(era: str):
    conn = get_conn()
    try:
        sets = conn.execute(
            "SELECT group_id, name, abbreviation, published_on, image_url "
            "FROM sets WHERE era = ? ORDER BY published_on",
            (era,),
        ).fetchall()

        if not sets:
            raise HTTPException(status_code=404, detail=f"No sets found for era '{era}'")

        group_ids = [s["group_id"] for s in sets]
        ph = ",".join("?" * len(group_ids))

        products = conn.execute(
            f"SELECT product_id, group_id, name, product_type "
            f"FROM products WHERE group_id IN ({ph})",
            group_ids,
        ).fetchall()

        history_map: dict = {}
        if products:
            product_ids = [p["product_id"] for p in products]
            ph2 = ",".join("?" * len(product_ids))
            rows = conn.execute(
                f"""
                SELECT product_id, captured_at,
                       low_price, mid_price, high_price, market_price
                FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY product_id
                               ORDER BY captured_at DESC
                           ) AS rn
                    FROM price_snapshots
                    WHERE product_id IN ({ph2})
                )
                WHERE rn <= 7
                ORDER BY product_id, captured_at ASC
                """,
                product_ids,
            ).fetchall()

            for row in rows:
                pid = row["product_id"]
                history_map.setdefault(pid, []).append({
                    "captured_at":  row["captured_at"],
                    "low_price":    row["low_price"],
                    "mid_price":    row["mid_price"],
                    "high_price":   row["high_price"],
                    "market_price": row["market_price"],
                })

        products_by_group: dict = {}
        for p in products:
            gid = p["group_id"]
            pid = p["product_id"]
            hist = history_map.get(pid, [])
            products_by_group.setdefault(gid, []).append({
                "product_id":   pid,
                "name":         p["name"],
                "product_type": p["product_type"],
                "latest":       hist[-1] if hist else None,
                "history":      hist,
            })

        return [
            {
                "group_id":     s["group_id"],
                "name":         s["name"],
                "abbreviation": s["abbreviation"],
                "published_on": (s["published_on"] or "")[:10],
                "image_url":    s["image_url"],
                "products":     products_by_group.get(s["group_id"], []),
            }
            for s in sets
        ]
    finally:
        conn.close()


@app.get("/api/hot")
def get_hot(era: Optional[str] = None):
    conn = get_conn()
    try:
        era_filter = "AND s.era = :era" if era else ""
        params = {"era": era}

        movers = conn.execute(f"""
            WITH ranked AS (
                SELECT
                    ps.product_id,
                    ps.market_price,
                    p.name         AS product_name,
                    p.product_type,
                    s.name         AS set_name,
                    s.abbreviation,
                    ROW_NUMBER() OVER (
                        PARTITION BY ps.product_id
                        ORDER BY ps.captured_at DESC
                    ) AS rn
                FROM price_snapshots ps
                JOIN products p ON p.product_id = ps.product_id
                JOIN sets     s ON s.group_id   = p.group_id
                WHERE ps.market_price IS NOT NULL AND ps.market_price > 0
                {era_filter}
            )
            SELECT
                cur.product_id,
                cur.product_name,
                cur.set_name,
                cur.abbreviation,
                cur.product_type,
                cur.market_price                                                            AS current_price,
                prev.market_price                                                           AS previous_price,
                ROUND(
                    (cur.market_price - prev.market_price) / prev.market_price * 100, 2
                )                                                                           AS pct_change
            FROM ranked cur
            JOIN ranked prev
              ON prev.product_id = cur.product_id AND prev.rn = 2
            WHERE cur.rn = 1 AND prev.market_price > 0
              AND cur.market_price > prev.market_price
            ORDER BY pct_change DESC
            LIMIT 5
        """, params).fetchall()

        if movers:
            return {"mode": "movers", "items": [dict(r) for r in movers]}

        valuable = conn.execute(f"""
            SELECT * FROM (
                SELECT
                    p.product_id,
                    p.name         AS product_name,
                    p.product_type,
                    s.name         AS set_name,
                    s.abbreviation,
                    ps.market_price AS current_price,
                    NULL            AS previous_price,
                    NULL            AS pct_change,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.product_id
                        ORDER BY ps.captured_at DESC
                    ) AS rn
                FROM price_snapshots ps
                JOIN products p ON p.product_id = ps.product_id
                JOIN sets     s ON s.group_id   = p.group_id
                WHERE ps.market_price IS NOT NULL AND ps.market_price > 0
                {era_filter}
            )
            WHERE rn = 1
            ORDER BY current_price DESC
            LIMIT 5
        """, params).fetchall()

        if not valuable:
            return {"mode": "empty", "items": []}

        return {"mode": "valuable", "items": [dict(r) for r in valuable]}
    finally:
        conn.close()


@app.get("/api/history/{product_id}")
def get_history(product_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT captured_at, low_price, mid_price, high_price, market_price "
            "FROM price_snapshots WHERE product_id = ? ORDER BY captured_at ASC",
            (product_id,),
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="No price history found")
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
