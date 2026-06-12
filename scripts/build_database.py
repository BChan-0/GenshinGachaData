import sqlite3
import pandas as pd

conn = sqlite3.connect(
    "../database/genshin.db"
)

df = pd.read_csv(
    "../csv/all_items.csv"
)

df.to_sql(
    "items",
    conn,
    if_exists="replace",
    index=False
)

conn.close()
