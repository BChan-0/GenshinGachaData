import json
import os

import pandas as pd

BASE_DIR = os.path.dirname(__file__)
RAW_PAIMON_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "raw", "paimon"))
CSV_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "csv"))

os.makedirs(CSV_DIR, exist_ok=True)

rows = []

for root, _, files in os.walk(RAW_PAIMON_DIR):
    for file in files:
        if not file.lower().endswith(".json"):
            continue

        banner_id_str = os.path.splitext(file)[0]
        try:
            banner_id = int(banner_id_str)
        except ValueError:
            continue

        file_path = os.path.join(root, file)
        with open(file_path, encoding="utf8") as f:
            data = json.load(f)

        timestamp = data.get("time")
        for item in data.get("list", []):
            rows.append({
                "banner_id": banner_id,
                "timestamp": timestamp,
                "name": item.get("name"),
                "type": item.get("type"),
                "count": item.get("count"),
                "guaranteed": item.get("guaranteed"),
            })

if not rows:
    raise SystemExit(
        f"No JSON files found in {RAW_PAIMON_DIR}."
        " Please download paimon data into raw/paimon first."
    )

out_path = os.path.join(CSV_DIR, "all_items.csv")

df = pd.DataFrame(rows)
df.to_csv(out_path, index=False)
print(f"Wrote {len(df)} rows to {out_path}")

character_df = df[
    df["type"] == "character"
]

weapon_df = df[
    df["type"] == "weapon"
]

character_df.to_csv(
    "../csv/character_distribution.csv",
    index=False
)

weapon_df.to_csv(
    "../csv/weapon_distribution.csv",
    index=False
)

summary = (
    df.groupby("banner_id")
    .agg(
        total_pulls=("count", "sum"),
        total_guarantees=("guaranteed", "sum"),
        unique_items=("name", "count")
    )
    .reset_index()
)

summary.to_csv(
    "../csv/banner_summary.csv",
    index=False
)
