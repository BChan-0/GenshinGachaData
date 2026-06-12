import pandas as pd

df = pd.read_csv(
    "../csv/character_distribution.csv"
)

five_stars = [
    "furina",
    "nahida",
    "raiden shogun",
    "arlecchino",
    "mavuika",
]

five_df = df[
    df["name"].isin(five_stars)
]

five_df.to_csv(
    "../csv/five_star_distribution.csv",
    index=False
)
