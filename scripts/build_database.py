"""Load every CSV the pipeline produces into a single sqlite database.

Tables (each replaced on every run, so reruns are idempotent):
  pulls              individual per-pull data        (csv/pulls.csv)
  items              flat aggregate items (legacy)   (csv/all_items.csv)
  banners            banner metadata                 (csv/banners.csv)
  banner_summary     per-banner aggregate totals     (csv/aggregate/*.csv)
  item_popularity
  pity_distribution
  pull_by_day
  constellation

Whatever CSVs are missing are simply skipped, so you can build the database
after running only the aggregate track, only the individual track, or both.
"""
import os
import sqlite3

import pandas as pd

import paths

# table_name -> csv path
SOURCES = {
    "pulls": os.path.join(paths.CSV, "pulls.csv"),
    "items": os.path.join(paths.CSV, "all_items.csv"),
    "banners": os.path.join(paths.CSV, "banners.csv"),
    "banner_summary": os.path.join(paths.CSV_AGG, "banner_summary.csv"),
    "item_popularity": os.path.join(paths.CSV_AGG, "item_popularity.csv"),
    "pity_distribution": os.path.join(paths.CSV_AGG, "pity_distribution.csv"),
    "pull_by_day": os.path.join(paths.CSV_AGG, "pull_by_day.csv"),
    "constellation": os.path.join(paths.CSV_AGG, "constellation.csv"),
}


def main():
    paths.ensure_dirs(paths.DB_DIR)
    conn = sqlite3.connect(paths.DB)
    try:
        loaded = 0
        for table, csv_path in SOURCES.items():
            if not os.path.exists(csv_path):
                print("  skip {} (no {})".format(table, os.path.relpath(csv_path, paths.ROOT)))
                continue
            df = pd.read_csv(csv_path)
            df.to_sql(table, conn, if_exists="replace", index=False)
            print("  loaded {} rows -> table `{}`".format(len(df), table))
            loaded += 1
    finally:
        conn.close()

    print("\nDone. {} table(s) loaded into {}".format(loaded, paths.DB))


if __name__ == "__main__":
    main()
