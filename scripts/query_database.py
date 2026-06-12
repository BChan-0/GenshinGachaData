import sqlite3
import pandas as pd

conn = sqlite3.connect(
    "../database/genshin.db"
)

query = """
SELECT
    name,
    SUM(count) AS pulls
FROM items
GROUP BY name
ORDER BY pulls DESC
"""

df = pd.read_sql(
    query,
    conn
)

print(df.head(20))

conn.close()
