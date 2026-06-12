"""Flatten the paimon.moe AGGREGATE JSON into tidy CSVs (csv/aggregate/).

Reminder: this is community-wide aggregate data, not individual pulls. Outputs:

  csv/all_items.csv              kept for backwards compatibility (table `items`)
  csv/aggregate/banner_summary.csv     one row per banner (totals, avg pity)
  csv/aggregate/item_popularity.csv    one row per item per banner (+ rarity)
  csv/aggregate/pity_distribution.csv  long form of the per-pity 5*/4* counts
  csv/aggregate/pull_by_day.csv        share of pulls over time
  csv/aggregate/constellation.csv      constellation/refinement distribution

Rarity (when available from download_reference.py) is joined onto item rows.
Note: paimon's per-item `guaranteed` is a COUNT of pulls won off a guarantee,
not a boolean -- it is surfaced as `guaranteed_pull_count`, never summed as a flag.
"""
import json
import os

import pandas as pd

import paths

# pityCount keys -> the rarity class label we expose
RARITY_CLASSES = ["legendary", "rare"]


def banner_type_from_id(banner_id):
    return {
        2: "Standard", 3: "Character Event", 4: "Weapon Event",
        5: "Chronicled Wish", 1: "Beginner",
    }.get(banner_id // 100000, "Unknown")


def load_rarity_lookup():
    path = os.path.join(paths.RAW_REFERENCE, "rarity_lookup.json")
    if os.path.exists(path):
        with open(path, encoding="utf8") as f:
            return json.load(f)
    return {}


def load_banners():
    """Yield (banner_id, data) for every downloaded paimon JSON."""
    for fname in sorted(os.listdir(paths.RAW_PAIMON)):
        if not fname.endswith(".json"):
            continue
        try:
            banner_id = int(os.path.splitext(fname)[0])
        except ValueError:
            continue
        with open(os.path.join(paths.RAW_PAIMON, fname), encoding="utf8") as f:
            yield banner_id, json.load(f)


def main():
    paths.ensure_dirs(paths.CSV, paths.CSV_AGG)
    rarity_lookup = load_rarity_lookup()

    item_rows = []
    summary_rows = []
    pity_rows = []
    day_rows = []
    constellation_rows = []

    for banner_id, data in load_banners():
        btype = banner_type_from_id(banner_id)

        # --- per-item popularity ---
        for item in data.get("list", []):
            item_rows.append({
                "banner_id": banner_id,
                "banner_type": btype,
                "name": item.get("name"),
                "type": item.get("type"),
                "rarity": rarity_lookup.get(item.get("name")),
                "count": item.get("count"),
                "guaranteed_pull_count": item.get("guaranteed"),
            })

        # --- banner summary ---
        total = data.get("total", {}) or {}
        pity_avg = data.get("pityAverage", {}) or {}
        median = data.get("median", {}) or {}
        featured = _detect_featured(data.get("list", []), rarity_lookup)
        summary_rows.append({
            "banner_id": banner_id,
            "banner_type": btype,
            "snapshot_time": data.get("time"),
            "featured_5star": ", ".join(featured),
            "total_pulls": total.get("all"),
            "total_users": total.get("users"),
            "legendary_pulls": total.get("legendary"),
            "rare_pulls": total.get("rare"),
            "pity_avg_legendary": pity_avg.get("legendary"),
            "pity_avg_rare": pity_avg.get("rare"),
            "pity_median_legendary": median.get("legendary"),
        })

        # --- pity distribution (long form) ---
        pity_count = data.get("pityCount", {}) or {}
        for rarity_class in RARITY_CLASSES:
            for idx, count in enumerate(pity_count.get(rarity_class, []) or []):
                pity_rows.append({
                    "banner_id": banner_id,
                    "rarity_class": rarity_class,
                    "pity_index": idx + 1,  # 1-indexed
                    "count": count,
                })

        # --- pulls by day ---
        for entry in data.get("pullByDay", []) or []:
            day_rows.append({
                "banner_id": banner_id,
                "day": entry.get("day"),
                "percentage": entry.get("percentage"),
            })

        # --- constellation / refinement distribution ---
        for name, levels in (data.get("constellation", {}) or {}).items():
            for level, count in enumerate(levels or []):
                constellation_rows.append({
                    "banner_id": banner_id,
                    "name": name,
                    "constellation_level": level,
                    "count": count,
                })

    if not item_rows:
        raise SystemExit(
            "No banner JSON files found in {}. Run download_paimon.py first."
            .format(paths.RAW_PAIMON))

    items_df = pd.DataFrame(item_rows)
    # Backwards-compatible flat file (loaded as table `items`).
    items_df.to_csv(os.path.join(paths.CSV, "all_items.csv"), index=False)

    _write(items_df, "item_popularity.csv")
    _write(pd.DataFrame(summary_rows), "banner_summary.csv")
    _write(pd.DataFrame(pity_rows), "pity_distribution.csv")
    _write(pd.DataFrame(day_rows), "pull_by_day.csv")
    _write(pd.DataFrame(constellation_rows), "constellation.csv")

    print("Parsed {} banners, {} item rows.".format(
        len(summary_rows), len(item_rows)))


def _detect_featured(items, rarity_lookup, multiplier=3):
    import statistics
    if rarity_lookup:
        fives = [(it["name"], it["count"]) for it in items
                 if rarity_lookup.get(it["name"]) == 5]
    else:
        fives = [(it["name"], it["count"]) for it in items]
    counts = [c for _, c in fives if c is not None]
    if not counts:
        return []
    threshold = multiplier * statistics.median(counts)
    return [name for name, count in sorted(fives, key=lambda x: -(x[1] or 0))
            if (count or 0) > threshold]


def _write(df, filename):
    out_path = os.path.join(paths.CSV_AGG, filename)
    df.to_csv(out_path, index=False)
    print("  wrote {} rows -> {}".format(len(df), out_path))


if __name__ == "__main__":
    main()
