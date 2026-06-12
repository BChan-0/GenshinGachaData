"""Quick bar chart of the 20 most-pulled characters (aggregate data).

Reads csv/aggregate/item_popularity.csv produced by parse_paimon.py.
"""
import os

import pandas as pd
import matplotlib.pyplot as plt

import paths

df = pd.read_csv(os.path.join(paths.CSV_AGG, "item_popularity.csv"))

characters = df[df["type"] == "character"]

top20 = (
    characters.groupby("name")["count"]
    .sum()
    .sort_values(ascending=False)
    .head(20)
)

top20.plot.bar()
plt.title("Top 20 most-pulled characters (community aggregate)")
plt.tight_layout()
plt.show()
