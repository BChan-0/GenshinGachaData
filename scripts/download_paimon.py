import json
import os
import time
import requests

os.makedirs("../raw/paimon", exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

banner_ids = [
    200001,
    300098,
    300099,
    300101,
    400100,
    500005,
    500006
]

for banner_id in banner_ids:

    print("Downloading", banner_id)

    url = f"https://api.paimon.moe/wish?banner={banner_id}"

    r = requests.get(
        url,
        headers=HEADERS
    )

    r.raise_for_status()

    with open(
        f"../raw/paimon/{banner_id}.json",
        "w",
        encoding="utf8"
    ) as f:

        json.dump(
            r.json(),
            f,
            indent=2,
            ensure_ascii=False
        )

    time.sleep(.2)
