"""Build csv/banners.csv: one row of metadata per downloaded paimon banner.

Columns: banner_id, banner_type, snapshot_time, featured_5star

We deliberately avoid the brittle approach of mapping paimon-moe's banners.js
(which has no numeric IDs) by array position. Instead everything is derived from
data we already have:
  - banner_type  : from the banner ID range (200xxx standard, 3xxxxx character
                   event, 4xxxxx weapon event, 5xxxxx chronicled).
  - snapshot_time: the JSON's own `time` field (when paimon last aggregated it).
  - featured_5star: the 5-star item(s) whose pull count towers over the other
                    5-stars on that banner -- i.e. the rate-up unit(s). The
                    standard banner has no rate-up, so this is empty for it.

Uses raw/reference/rarity_lookup.json if present (from download_reference.py);
without it, falls back to a count-threshold over all items, which still surfaces
the featured units because their counts dominate.
"""
import json
import os
import statistics

import pandas as pd

import paths

FEATURED_COUNT_MULTIPLIER = 3  # featured 5* count is far above the pool median


def banner_type_from_id(banner_id):
    prefix = banner_id // 100000
    return {
        2: "Standard",
        3: "Character Event",
        4: "Weapon Event",
        5: "Chronicled Wish",
        1: "Beginner",
    }.get(prefix, "Unknown")


def load_rarity_lookup():
    path = os.path.join(paths.RAW_REFERENCE, "rarity_lookup.json")
    if os.path.exists(path):
        with open(path, encoding="utf8") as f:
            return json.load(f)
    return {}


def detect_featured(items, rarity_lookup):
    """Return the rate-up 5-star slug(s) for a banner, highest count first."""
    if rarity_lookup:
        fives = [(it["name"], it["count"]) for it in items
                 if rarity_lookup.get(it["name"]) == 5]
    else:
        # No rarity data: consider all items; the rate-up units still dominate.
        fives = [(it["name"], it["count"]) for it in items]

    counts = [c for _, c in fives if c is not None]
    if not counts:
        return []

    threshold = FEATURED_COUNT_MULTIPLIER * statistics.median(counts)
    featured = [name for name, count in sorted(fives, key=lambda x: -(x[1] or 0))
                if (count or 0) > threshold]
    return featured


def main():
    paths.ensure_dirs(paths.CSV)
    rarity_lookup = load_rarity_lookup()

    rows = []
    for fname in sorted(os.listdir(paths.RAW_PAIMON)):
        if not fname.endswith(".json"):
            continue
        try:
            banner_id = int(os.path.splitext(fname)[0])
        except ValueError:
            continue

        with open(os.path.join(paths.RAW_PAIMON, fname), encoding="utf8") as f:
            data = json.load(f)

        featured = detect_featured(data.get("list", []), rarity_lookup)
        rows.append({
            "banner_id": banner_id,
            "banner_type": banner_type_from_id(banner_id),
            "snapshot_time": data.get("time"),
            "featured_5star": ", ".join(featured),
        })

    if not rows:
        raise SystemExit(
            "No banner JSON files found in {}. Run download_paimon.py first."
            .format(paths.RAW_PAIMON))

    df = pd.DataFrame(rows).sort_values("banner_id")
    out_path = os.path.join(paths.CSV, "banners.csv")
    df.to_csv(out_path, index=False)
    print("Wrote {} banners to {}".format(len(df), out_path))


if __name__ == "__main__":
    main()
