"""Download AGGREGATE wish statistics from paimon.moe for every banner.

paimon.moe's /wish?banner=<id> endpoint returns community-wide aggregate stats
(how many times each item was pulled across all ~3.4M tracked users, average
pity, etc.) -- NOT individual pull histories. For per-pull data see the UIGF
scripts (download_uigf.py / parse_uigf.py).

Banner IDs are sparse but fall into known contiguous ranges:
    200001            -> Standard (Wanderlust Invocation)
    300009 - 300101   -> Character Event banners
    400008 - 400100   -> Weapon Event banners
    500001 - 500006   -> Chronicled Wish banners
A non-existent banner returns HTTP 404 and is simply skipped.
"""
import json
import os
import time

import requests

import paths

HEADERS = {"User-Agent": "Mozilla/5.0"}

# (start, end) inclusive ranges, scanned with a miss-streak guard. The bounds
# are generous so newly added banners get picked up automatically; scanning
# stops for a range once MAX_MISS_STREAK consecutive IDs come back missing.
BANNER_RANGES = [
    (200001, 200005),
    (300009, 300140),
    (400008, 400140),
    (500001, 500020),
]
MAX_MISS_STREAK = 8
REQUEST_TIMEOUT = 15
SLEEP_SECONDS = 0.2


def fetch_banner(banner_id):
    """Return parsed JSON for a banner, or None if it does not exist (404)."""
    url = "https://api.paimon.moe/wish?banner={}".format(banner_id)
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    if resp.status_code in (400, 404):
        return None
    resp.raise_for_status()
    return resp.json()


def main():
    paths.ensure_dirs(paths.RAW_PAIMON)

    downloaded = 0
    skipped = 0

    for start, end in BANNER_RANGES:
        miss_streak = 0
        for banner_id in range(start, end + 1):
            out_path = os.path.join(paths.RAW_PAIMON, "{}.json".format(banner_id))

            if os.path.exists(out_path):
                skipped += 1
                miss_streak = 0
                continue

            data = fetch_banner(banner_id)
            if data is None:
                miss_streak += 1
                if miss_streak >= MAX_MISS_STREAK:
                    print("  range {}-{}: stopping after {} misses".format(
                        start, end, miss_streak))
                    break
                continue

            miss_streak = 0
            with open(out_path, "w", encoding="utf8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            downloaded += 1
            print("Downloaded", banner_id)
            time.sleep(SLEEP_SECONDS)

    total = len([n for n in os.listdir(paths.RAW_PAIMON) if n.endswith(".json")])
    print("\nDone. {} new, {} already present, {} banner files total.".format(
        downloaded, skipped, total))


if __name__ == "__main__":
    main()
