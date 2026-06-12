"""A few example queries against database/genshin.db.

Run build_database.py first. Queries degrade gracefully if a table is absent
(e.g. you only built the aggregate track, so there is no `pulls` table yet).
"""
import sqlite3

import pandas as pd

import paths


def run(conn, title, query):
    try:
        df = pd.read_sql(query, conn)
    except Exception as exc:
        print("[skip] {}: {}".format(title, exc))
        return
    print("\n=== {} ===".format(title))
    print(df.head(20).to_string(index=False))


def main():
    conn = sqlite3.connect(paths.DB)
    try:
        # Aggregate: most-pulled items across all banners.
        run(conn, "Most pulled items (aggregate)", """
            SELECT name, SUM(count) AS pulls
            FROM items
            GROUP BY name
            ORDER BY pulls DESC
        """)

        # Individual: pulls per banner in the per-pull dataset.
        run(conn, "Pulls per banner (individual)", """
            SELECT banner, COUNT(*) AS pulls,
                   SUM(rarity = 5) AS five_stars
            FROM pulls
            GROUP BY banner
            ORDER BY pulls DESC
        """)

        # Individual: every 5-star with the pity it came at.
        run(conn, "5-star pulls and their pity (individual)", """
            SELECT date, banner, result, pity
            FROM pulls
            WHERE rarity = 5
            ORDER BY date
        """)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
