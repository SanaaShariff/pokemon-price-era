# Pokemon Price Aggregator

Seeds a local SQLite database with sealed product prices for Pokemon TCG sets, sourced from [tcgcsv.com](https://tcgcsv.com).

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

## Usage

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests
python seed.py
```

The script prints progress as it runs. Expect ~2 minutes for a full seed across all 37 sets.
