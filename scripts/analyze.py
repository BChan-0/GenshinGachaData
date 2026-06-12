import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv(
    "../csv/character_distribution.csv"
)

top20 = (
    df.groupby("name")["count"]
      .sum()
      .sort_values(ascending=False)
      .head(20)
)

top20.plot.bar()

plt.tight_layout()
plt.show()
