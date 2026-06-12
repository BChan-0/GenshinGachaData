# -*- coding: utf-8 -*-
# NOTE: run with python3.
"""Import the OneBST/GI_gacha_dataset bulk corpus into csv/pulls.csv.

This is a SEPARATE source from the UIGF scrape: OneBST is a large, voluntarily
published collection of real Genshin wish histories stored as CSV (not UIGF
JSON), so the UIGF pipeline can't read it. This script normalises those CSVs
into the same per-pull records and reuses parse_uigf's pity/region/anonymise
logic, so the output schema matches pulls.csv exactly.

Two sub-datasets (https://github.com/OneBST/GI_gacha_dataset):

  dataset_02  ~200k pulls. Plain CSV in the git repo, one folder per account
              (0001, 0002, ...), each with gachaNNN.csv where NNN is the pool
              (100/200/301/302). Columns are Chinese:
                  抽卡时间(time), 名称(name), 类别(type), 星级(rarity)
              No UID and no per-pull id -- the account is the folder number and
              chronological order is the CSV row order.

  dataset_03  ~15.6M pulls across 16,289 accounts. Shipped as a password-
              protected 7z ("OneBST"); each extracted CSV is one account named
              by the last 4 UID digits. Columns:
                  name, gacha_type, item_type, rank_type, gacha_id, gacha_time
              Pools: 100 beginner, 200 standard, 301 & 400 character, 302 weapon.

dataset_02 can be fetched directly over HTTP (set MODE=02, the default).
dataset_03 must be downloaded and extracted by hand first (this environment has
no 7z); point ONEBST_03_DIR at the extracted player_data folder.

Usage:
  python3 scripts/import_onebst.py                 # fetch dataset_02 over HTTP
  python3 scripts/import_onebst.py --accounts 30   # limit dataset_02 accounts
  ONEBST_03_DIR=/path/to/player_data python3 scripts/import_onebst.py --mode 03

Output: APPENDS to csv/pulls.csv (deduped by player_id against existing rows),
so run parse_uigf.py first if you want both sources combined, then this.
"""
import argparse
import csv
import glob
import io
import os
import urllib.request

import pandas as pd

import paths
import parse_uigf  # reuse pity/region/anonymise + schema

RAW_BASE = ("https://raw.githubusercontent.com/OneBST/GI_gacha_dataset/main/"
            "GI_gacha_dataset_02")
HTTP_TIMEOUT = 15

# dataset_02 gachaNNN.csv filename -> pool code (matches UIGF gacha_type).
POOL_FILES = {"100": "100", "200": "200", "301": "301", "302": "302"}

# Chinese item-type -> the item_type label used elsewhere.
ITEM_TYPE_CN = {"角色": "Character", "武器": "Weapon"}


def _norm_record(name, item_type, rarity, time_str, pool, seq):
    """Build a UIGF-shaped record so parse_uigf.process_account can consume it."""
    return {
        "name": name,
        "item_type": ITEM_TYPE_CN.get(item_type, item_type),
        "rank_type": rarity,
        "time": time_str,
        # 400 (parallel character banner) shares 301's pool; parse_uigf handles it.
        "uigf_gacha_type": pool,
        "gacha_type": pool,
        # synthesise a monotonic id from row order: CSVs are already in pull
        # order, and intra-second 10-pulls need a stable tiebreaker.
        "id": str(seq),
    }


# --- dataset_02: plain CSV over HTTP -----------------------------------------

def _fetch(url):
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "onebst-import"}),
            timeout=HTTP_TIMEOUT)
        return resp.read().decode("utf-8-sig")  # -sig strips the BOM
    except Exception:
        return None


def _parse_csv_02(text, pool, start_seq):
    """dataset_02 rows: 抽卡时间, 名称, 类别, 星级."""
    records = []
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return records
    # Skip the header if present (first cell is the Chinese 抽卡时间).
    data = rows[1:] if rows[0] and "抽卡" in rows[0][0] else rows
    for offset, row in enumerate(data):
        if len(row) < 4:
            continue
        time_str, name, item_type, rarity = row[0], row[1], row[2], row[3]
        records.append(_norm_record(
            name, item_type, rarity, time_str, pool, start_seq + offset))
    return records


def load_dataset_02(max_accounts):
    """Yield (account_id, records) by fetching dataset_02 folders over HTTP."""
    account = 0
    while max_accounts is None or account < max_accounts:
        account += 1
        folder = "{:04d}".format(account)
        records = []
        seq = 0
        found_any = False
        for pool_name, pool in POOL_FILES.items():
            text = _fetch("{}/{}/gacha{}.csv".format(RAW_BASE, folder, pool_name))
            if text is None:
                continue
            found_any = True
            recs = _parse_csv_02(text, pool, seq)
            seq += len(recs) + 1
            records.extend(recs)
        if not found_any:
            break  # ran past the last account folder
        if records:
            # No real UID in dataset_02 -- key the player by dataset+folder.
            yield "onebst02-{}".format(folder), records


# --- dataset_03: extracted CSV on disk ---------------------------------------

def _parse_csv_03(path):
    """dataset_03 rows: name, gacha_type, item_type, rank_type, gacha_id, gacha_time."""
    records = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            pool = (row.get("gacha_type") or "").strip()
            records.append(_norm_record(
                row.get("name", ""),
                row.get("item_type", ""),
                row.get("rank_type", ""),
                row.get("gacha_time", ""),
                pool,
                # prefer the real gacha_id as the ordering key; fall back to row.
                _to_int(row.get("gacha_id"), i)))
    return records


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_dataset_03(directory):
    """Yield (uid_suffix, records) from extracted dataset_03 CSVs."""
    files = sorted(glob.glob(os.path.join(directory, "*.csv")))
    if not files:
        raise SystemExit(
            "No CSVs in {}. Extract the dataset_03 7z (password 'OneBST') and "
            "point ONEBST_03_DIR at the player_data folder.".format(directory))
    for path in files:
        # filename's last 4 chars before .csv are the UID suffix.
        stem = os.path.splitext(os.path.basename(path))[0]
        yield "onebst03-{}".format(stem[-4:]), _parse_csv_03(path)


# --- driver ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Import OneBST gacha dataset.")
    ap.add_argument("--mode", choices=["02", "03"], default="02",
                    help="02 = fetch plain CSV over HTTP (default); "
                         "03 = read extracted CSVs from ONEBST_03_DIR.")
    ap.add_argument("--accounts", type=int, default=None,
                    help="dataset_02 only: cap the number of accounts fetched.")
    args = ap.parse_args()

    paths.ensure_dirs(paths.CSV)

    if args.mode == "02":
        source = load_dataset_02(args.accounts)
    else:
        directory = os.environ.get("ONEBST_03_DIR")
        if not directory:
            raise SystemExit("Set ONEBST_03_DIR to the extracted player_data folder.")
        source = load_dataset_03(directory)

    all_rows = []
    n_players = 0
    for account_key, records in source:
        if not records:
            continue
        # account_key stands in for the UID -> stable anonymised player_id.
        rows = parse_uigf.process_account(account_key, records)
        all_rows.extend(rows)
        n_players += 1
        if n_players % 25 == 0:
            print("  ...{} accounts, {} pulls so far".format(n_players, len(all_rows)))

    if not all_rows:
        raise SystemExit("No pulls imported from OneBST.")

    new_df = pd.DataFrame(all_rows, columns=parse_uigf.OUTPUT_COLUMNS)
    out_path = os.path.join(paths.CSV, "pulls.csv")

    # Append to an existing pulls.csv, dropping any player already present so
    # re-runs and overlap with the UIGF data don't double-count.
    if os.path.exists(out_path):
        existing = pd.read_csv(out_path)
        new_players = set(new_df["player_id"]) - set(existing["player_id"])
        new_df = new_df[new_df["player_id"].isin(new_players)]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(out_path, index=False)
    print("\nImported {} OneBST account(s), {} new pulls. pulls.csv now {} rows."
          .format(n_players, len(new_df), len(combined)))


if __name__ == "__main__":
    main()
