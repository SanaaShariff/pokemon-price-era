# Pokemon Price Aggregator

Tracks sealed product prices for Pokemon TCG sets in a local SQLite database, sourced from [tcgcsv.com](https://tcgcsv.com).

## Database

Three tables in `pokemon_prices.db`:

- **sets** — one row per set (group_id, name, abbreviation, era, published_on)
- **products** — sealed products filtered to Booster Boxes, Elite Trainer Boxes, and Booster Packs
- **price_snapshots** — low, mid, high, and market prices captured at a point in time

## Sets covered

| Era | Abbreviations |
|-----|--------------|
| Sword & Shield | SSH, RCL, DAA, CPA, VIV, SHF, BST, CRE, EVS, CEL, FST, BRS, ASR, PGO, LOR, SIT, CRZ |
| Scarlet & Violet | SVI, PAL, OBF, MEW, PAR, PAF, TEF, TWM, SFA, SCR, SSP, PRE, JTG, DRI, BLK, WHT |
| Mega Evolution | MEG, PFL, ASC, POR |

## Scripts

### `seed.py`

One-time setup. Creates the database tables and populates sets, products, and an initial price snapshot.

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests
python seed.py
```

Expect ~2 minutes for a full seed across all 37 sets.

### `snapshot.py`

Run daily to capture current prices. Fetches prices for each set and inserts one row per product into `price_snapshots`, skipping any products already snapshotted today.

```bash
python snapshot.py
```
