"""Turn UIGF wish-history exports (raw/uigf/*.json) into csv/pulls.csv.

This is the INDIVIDUAL, per-pull dataset. Each row is one wish:

    date, time, location, result, rarity, pity, banner   <- requested columns
    + player_id, banner_type, pity_4                      <- helper columns

How each column is produced:
  date/time  : split from UIGF `time` ("YYYY-MM-DD HH:MM:SS", server-local).
  location   : account server region, from the UID's first digit (derived
               BEFORE anonymisation so we don't lose it).
  result     : the item name.
  rarity     : UIGF `rank_type` (3/4/5), validated.
  pity       : 5-star pity, COMPUTED by walking each player's pulls in order
               within a pity pool and resetting after each 5-star.
  banner     : human label for the pull's banner pool.
  player_id  : salted SHA-256 of the UID (pseudonymous, see note below).
  pity_4     : the independent 4-star pity counter.

Pity notes:
  * Pity is grouped by `uigf_gacha_type`, which already merges the two parallel
    character-event pools (301 + 400) into one logical pool. Standard, weapon,
    chronicled and beginner pools are independent.
  * 5-star and 4-star counters are independent: a 5-star does not reset the
    4-star counter or vice versa.
  * Convention: pity is 1-indexed and inclusive -- a 5-star pulled on the 76th
    wish has pity 76, and the counter resets to 0 right after.
  * The first stretch of each pool is left-censored (an export rarely begins at
    a player's very first wish), so the first pity value per pool is a lower
    bound. We emit it anyway.

Privacy note: UIDs live in a small, enumerable space, so a salted hash is a
pseudonym rather than true anonymisation. Set PULLS_SALT in the environment to
keep player_id stable across runs without committing the salt.
"""
import glob
import hashlib
import json
import os

import pandas as pd

import paths

SALT = os.environ.get("PULLS_SALT", "genshin-gacha-data")

# uigf_gacha_type -> human banner label
BANNER_LABELS = {
    "100": "Beginner",
    "200": "Standard",
    "301": "Character Event",
    "302": "Weapon Event",
    "500": "Chronicled Wish",
}

# UID first digit -> account server region.
# China spans 1/2/3 (official "Celestia" server cn_gf01) and 5 (bilibili
# "Irminsul" server cn_qd01) -- all labelled "China" since this column is a
# coarse region, not a sub-server. Digit 4 is intentionally absent: it is not a
# Genshin server (it's the Tears of Themis game id), so it falls through to
# "Unknown". Sources: UIGF-org id.md, genshin.py, SIMNet, hoyo-buddy.
REGION_BY_PREFIX = {
    "1": "China", "2": "China", "3": "China", "5": "China",
    "6": "America", "7": "Europe", "8": "Asia",
    "9": "TW/HK/MO",
}

OUTPUT_COLUMNS = [
    "date", "time", "location", "result", "rarity", "pity", "banner",
    "player_id", "banner_type", "pity_4",
]


def region_from_uid(uid):
    # Genshin UIDs are normally 9 digits (1-char prefix). The Asia server
    # overflowed its 9-digit space, so newer Asia accounts have 10-digit UIDs
    # beginning "18" -- a naive first-char read would mislabel those as China.
    # Key on everything except the trailing 8 account digits to handle both.
    prefix = str(uid)[:-8] or str(uid)[:1]
    if prefix == "18":
        return "Asia"
    return REGION_BY_PREFIX.get(prefix[:1], "Unknown")


def _load_name_lookup():
    """{chinese|english|slug -> slug} from download_reference.py, or {} if absent.

    Real exports carry item names in whatever language the player's client used,
    so we normalise every name to one English slug for consistency across
    sources. Without the lookup, names are passed through unchanged.
    """
    path = os.path.join(paths.RAW_REFERENCE, "name_lookup.json")
    if os.path.exists(path):
        with open(path, encoding="utf8") as f:
            return json.load(f)
    return {}


NAME_LOOKUP = _load_name_lookup()


def normalize_name(name):
    if not name:
        return name
    return NAME_LOOKUP.get(name, name)


def anonymize(uid):
    digest = hashlib.sha256((SALT + str(uid)).encode("utf8")).hexdigest()
    return "player_" + digest[:10]


def iter_accounts(doc):
    """Yield (uid, records) from either UIGF v2.x (flat) or v4.0 (nested)."""
    if isinstance(doc.get("list"), list):
        uid = (doc.get("info") or {}).get("uid")
        yield uid, doc["list"]
    elif isinstance(doc.get("hk4e"), list):  # UIGF v4.0 multi-account
        for account in doc["hk4e"]:
            yield account.get("uid"), account.get("list", [])


def uigf_pool(record):
    """The pity pool key: prefer uigf_gacha_type, fall back to gacha_type."""
    pool = record.get("uigf_gacha_type") or record.get("gacha_type")
    # gacha_type 400 is the parallel character banner -> same pool as 301.
    return "301" if str(pool) == "400" else str(pool)


def sort_key(record):
    # time first, then id as int (the only intra-second tiebreaker for 10-pulls)
    raw_id = record.get("id") or "0"
    try:
        id_num = int(raw_id)
    except (TypeError, ValueError):
        id_num = 0
    return (record.get("time") or "", id_num)


def process_account(uid, records):
    region = region_from_uid(uid)
    player_id = anonymize(uid)

    ordered = sorted(records, key=sort_key)

    # Independent running pity counters per pool.
    pity5 = {}
    pity4 = {}
    rows = []

    for rec in ordered:
        pool = uigf_pool(rec)
        try:
            rarity = int(rec.get("rank_type"))
        except (TypeError, ValueError):
            continue
        if rarity not in (3, 4, 5):
            continue

        pity5[pool] = pity5.get(pool, 0) + 1
        pity4[pool] = pity4.get(pool, 0) + 1

        time_str = rec.get("time") or ""
        date_part, _, time_part = time_str.partition(" ")

        rows.append({
            "date": date_part,
            "time": time_part,
            "location": region,
            "result": normalize_name(rec.get("name")),
            "rarity": rarity,
            "pity": pity5[pool],
            "banner": BANNER_LABELS.get(pool, "Unknown"),
            "player_id": player_id,
            "banner_type": pool,
            "pity_4": pity4[pool],
        })

        # Reset the matching counter AFTER recording the winning pull.
        if rarity == 5:
            pity5[pool] = 0
        if rarity == 4:
            pity4[pool] = 0

    return rows


def main():
    paths.ensure_dirs(paths.CSV)

    files = sorted(glob.glob(os.path.join(paths.RAW_UIGF, "*.json")))
    if not files:
        raise SystemExit(
            "No UIGF files in {}. Drop an export there, run download_uigf.py "
            "with a GITHUB_TOKEN, or keep the bundled sample_uigf.json."
            .format(paths.RAW_UIGF))

    # Dedup by UID across all files: the same player's export is often committed
    # to several repos (forks, mirrors, aggregators). Keep the richest export
    # (most records) per UID so a player's pulls aren't counted twice.
    best = {}  # uid -> (record_count, source_file, records)
    for path in files:
        try:
            with open(path, encoding="utf8") as f:
                doc = json.load(f)
        except (ValueError, OSError) as exc:
            print("  skipping {} ({})".format(os.path.basename(path), exc))
            continue

        for uid, records in iter_accounts(doc):
            if not uid or not records:
                continue
            previous = best.get(uid)
            if previous is None or len(records) > previous[0]:
                best[uid] = (len(records), os.path.basename(path), records)

    all_rows = []
    for uid in sorted(best):
        _, source, records = best[uid]
        account_rows = process_account(uid, records)
        all_rows.extend(account_rows)
        print("  uid {} -> {}: {} pulls (from {})".format(
            str(uid)[:1] + "...", region_from_uid(uid),
            len(account_rows), source))

    if not all_rows:
        raise SystemExit("No valid pulls parsed from the UIGF files.")

    print("\n{} unique player(s) after dedup.".format(len(best)))

    df = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
    out_path = os.path.join(paths.CSV, "pulls.csv")
    df.to_csv(out_path, index=False)
    print("\nWrote {} pulls to {}".format(len(df), out_path))


if __name__ == "__main__":
    main()
