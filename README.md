# GenshinGachaData

Python web scraper.

Created for HSYLC with public data.

A small pipeline that gathers Genshin Impact gacha (wish) data into CSVs and a
sqlite database. There are two separate datasets because they come from two
different kinds of sources:

| Dataset | Granularity | Source | Output |
|---|---|---|---|
| **Individual** | one row per pull | UIGF wish-history exports | `csv/pulls.csv` |
| **Aggregated** | community-wide totals | paimon.moe | `csv/aggregate/*.csv` |

> **Why two sources?** paimon.moe only publishes aggregate statistics. It has no
> per-pull rows, timestamps, or per-pull pity. So the individual columns
> (date, time, region, result, rarity, pity, banner) cannot come from
> paimon.moe.

## Setup

```bash
pip install -r requirements.txt
```

Every script reads its paths from `scripts/paths.py`, so you can run them from
the `scripts/` folder or the repo root.

## Individual dataset (`csv/pulls.csv`)

Columns: `date, time, location, result, rarity, pity, banner` (plus
`player_id`, `banner_type`, `pity_4`).

- `location` is the account **server region**, derived from the UID's first
  digit (America / Europe / Asia / TW-HK-MO / China).
- `pity` is **computed** by walking each player's pulls in time order and
  resetting after each 5★ (4★ pity is tracked independently in `pity_4`). Pity
  is grouped by `uigf_gacha_type`, so the two parallel character banners share a
  pool, while standard / weapon / chronicled are independent.
- UIDs are replaced with a **salted hash** (`player_id`). Set `PULLS_SALT` in the
  environment to keep IDs stable across runs. (UIDs are a small space, so this is
  a pseudonym, not perfect anonymisation.)

Three ways to get UIGF data into `raw/uigf/`:

1. **Bundled sample** — `raw/uigf/sample_uigf.json` ships in the repo, so the
   pipeline runs with zero setup.
2. **Your own files** — drop any UIGF `.json` export into `raw/uigf/`.
3. **GitHub scrape** — searches public repos for UIGF exports. GitHub *code*
   search needs a token:

   ```bash
   export GITHUB_TOKEN=ghp_your_token_here   # public-search scope is enough
   python3 scripts/download_uigf.py
   ```

Then build the dataset:

```bash
python3 scripts/parse_uigf.py        # -> csv/pulls.csv
```

> **Privacy:** raw UIGF exports contain real, plaintext account UIDs, so
> `raw/uigf/*` is gitignored (only the synthetic sample is committed).
> `csv/pulls.csv` is safe to share — UIDs are replaced with salted hashes.

### Getting more data

The scrape has four tunable levers, in `scripts/download_uigf.py`, weakest to
strongest:

1. **More depth per query** by raising `MAX_RESULTS_PER_QUERY` (200 → up to 1000).
2. **More breadth** by adding exporter signatures to `SEARCH_QUERIES`. Each distinct
   query reaches files the others miss.
3. **Targeted scope** by adding `repo:owner/name` or `user:someone` to a query to
   focus on a known source.
4. **Full-repo harvest** by adding `"owner/repo"` entries to
   the `REPOS` list. Code search only returns a capped subset per repo, but an
   aggregator repo can hold hundreds of exports; harvesting walks the repo's
   entire file tree and grabs every UIGF export (and bypasses code search's
   384 KB file-size limit). The repos shown in a scrape's output are good
   harvest candidates. (Note: most public UIGF repos are single-player, so true
   UIGF aggregators are rare — for bulk data see the OneBST import below.)

### Bulk import: the OneBST dataset (`import_onebst.py`)

[OneBST/GI_gacha_dataset](https://github.com/OneBST/GI_gacha_dataset) is the one
large public corpus of real, voluntarily-shared wish histories — but it's stored
as **CSV, not UIGF JSON**, so the scraper can't read it. `import_onebst.py`
normalises those CSVs into the same `pulls.csv` schema (reusing the pity / region
/ anonymisation logic) and appends them, deduping by player.

```bash
python3 scripts/download_reference.py    # recommended first: enables CN->slug names
python3 scripts/import_onebst.py                 # dataset_02 (~100 accounts, ~200k pulls) over HTTP
python3 scripts/import_onebst.py --accounts 20   # ...or cap how many accounts
```

- **dataset_02** (the default) is plain CSV in the repo and downloads directly —
  no token, no extraction.
- **dataset_03** (~16k accounts / 15.6M pulls) ships as a password-protected 7z
  (`OneBST`). This environment can't extract 7z, so download + extract it
  yourself, then point the importer at the extracted folder:
  ```bash
  ONEBST_03_DIR=/path/to/player_data python3 scripts/import_onebst.py --mode 03
  ```
- OneBST CSVs carry no UID, so `location` is `Unknown` (the account is a folder
  number, anonymised into `player_id` like everything else).

> **Name normalisation:** real exports use whatever language the player's client
> was set to (the scraped Chinese players' UIGF and OneBST are in Chinese).
> `download_reference.py` builds `name_lookup.json` (Chinese/English → English
> slug) so `parse_uigf.py` and `import_onebst.py` emit one consistent `result`
> slug that joins across sources and to the aggregate data.

## Aggregated dataset (`csv/aggregate/`)

```bash
python scripts/download_paimon.py        # downloads ~190 banners -> raw/paimon/
python scripts/download_reference.py     # optional: name->rarity lookup
python scripts/build_banner_metadata.py  # -> csv/banners.csv
python scripts/parse_paimon.py           # -> csv/aggregate/*.csv (+ csv/all_items.csv)
```

Aggregate outputs: `banner_summary.csv`, `item_popularity.csv`,
`pity_distribution.csv`, `pull_by_day.csv`, `constellation.csv`.

## Database & queries

```bash
python scripts/build_database.py     # loads every CSV present -> database/genshin.db
python scripts/query_database.py     # example queries over both datasets
```

## Charts (optional)

```bash
python scripts/analyze.py                      # top-20 pulled characters (aggregate)
python scripts/build_five_star_distribution.py # filter a few 5★ for comparison
```

## Script reference

| Script | Track | Purpose |
|---|---|---|
| `paths.py` | shared | path constants (import these, don't hardcode `../`) |
| `download_paimon.py` | aggregate | download all banners from paimon.moe |
| `download_reference.py` | shared | build `name → rarity` + `name → slug` lookups (optional) |
| `build_banner_metadata.py` | aggregate | `csv/banners.csv` |
| `parse_paimon.py` | aggregate | aggregate CSVs |
| `download_uigf.py` | individual | fetch UIGF exports (needs `GITHUB_TOKEN`) |
| `parse_uigf.py` | individual | `csv/pulls.csv` with computed pity |
| `import_onebst.py` | individual | bulk-import the OneBST CSV dataset into `pulls.csv` |
| `build_database.py` | shared | load all CSVs into sqlite |
| `query_database.py` | shared | example queries |
| `analyze.py`, `build_five_star_distribution.py` | aggregate | small chart helpers |
