"""Filter the aggregate item data down to a handful of 5-star characters.

Reads csv/aggregate/item_popularity.csv and writes csv/five_star_distribution.csv.
Edit FIVE_STARS to pick which units to compare.
"""
import os

import pandas as pd

import paths

FIVE_STARS = [
    "furina",
    "nahida",
    "raiden_shogun",
    "arlecchino",
    "mavuika",
]

df = pd.read_csv(os.path.join(paths.CSV_AGG, "item_popularity.csv"))

five_df = df[df["name"].isin(FIVE_STARS)]

out_path = os.path.join(paths.CSV, "five_star_distribution.csv")
five_df.to_csv(out_path, index=False)
print("Wrote {} rows to {}".format(len(five_df), out_path))
