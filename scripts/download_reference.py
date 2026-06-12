"""Build reference lookups from paimon-moe's open-source data files.

Produces two files in raw/reference/ (both OPTIONAL enhancements):

  rarity_lookup.json   slug -> rarity (3/4/5). parse_paimon.py uses it to add a
                       rarity column to the aggregate CSVs.
  name_lookup.json     Chinese name OR English display name -> English slug.
                       parse_uigf.py and import_onebst.py use it to NORMALISE
                       item names to one consistent slug, since real exports
                       come in whatever language the player's client used
                       (Chinese players' UIGF exports and the OneBST dataset are
                       in Chinese, which otherwise wouldn't join to each other
                       or to the slug-keyed aggregate data).

Source files (MadeBaruna/paimon-moe, raw GitHub):
    src/data/characters.js        slug + English name + rarity
    src/data/weaponList.js        slug + English name + rarity
    src/locales/items/zh.json     English name -> Chinese name
These are JavaScript modules / JSON; we extract with regex / json.load.

If GitHub is unreachable the script prints a message and exits 0; the rest of
the pipeline still works without the lookups.
"""
import json
import os
import re

import requests

import paths

HEADERS = {"User-Agent": "Mozilla/5.0"}
RAW_ROOT = "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/src/"
DATA_FILES = ["data/characters.js", "data/weaponList.js"]
ZH_LOCALE = "locales/items/zh.json"

# id: 'slug', ... rarity: N  (id always precedes rarity; non-greedy).
PAIR_RE = re.compile(r"id:\s*'([^']+)',[\s\S]{0,120}?rarity:\s*([1-5])")
# slug <-> English name. Names may use single OR double quotes (e.g. "Amos' Bow").
ID_NAME_RE = re.compile(r"id:\s*'([^']+)',\s*name:\s*(?:'([^']*)'|\"([^\"]*)\")")
NAME_ID_RE = re.compile(r"name:\s*(?:'([^']*)'|\"([^\"]*)\"),\s*id:\s*'([^']+)'")

REQUEST_TIMEOUT = 15


def _fetch(rel_path):
    try:
        resp = requests.get(RAW_ROOT + rel_path, headers=HEADERS,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print("  could not fetch {} ({})".format(rel_path, exc))
        return None


def build_rarity_lookup(texts):
    lookup = {}
    for text in texts:
        for slug, rarity in PAIR_RE.findall(text):
            lookup[slug] = int(rarity)
    return lookup


def build_name_lookup(texts, zh_text):
    """Return {chinese_or_english_name: slug}, self-mapping slugs too."""
    en_to_slug = {}
    for text in texts:
        for slug, n1, n2 in ID_NAME_RE.findall(text):
            en_to_slug[n1 or n2] = slug
        for n1, n2, slug in NAME_ID_RE.findall(text):
            en_to_slug.setdefault(n1 or n2, slug)

    name_lookup = {}
    # English display name -> slug, and slug -> itself (idempotent normalisation).
    for english, slug in en_to_slug.items():
        name_lookup[english] = slug
        name_lookup[slug] = slug
    # Chinese name -> slug, chained through English via the zh locale.
    if zh_text:
        for english, chinese in json.loads(zh_text).items():
            slug = en_to_slug.get(english)
            if slug:
                name_lookup[chinese] = slug
    return name_lookup


def main():
    paths.ensure_dirs(paths.RAW_REFERENCE)

    texts = [t for t in (_fetch(f) for f in DATA_FILES) if t is not None]
    if not texts:
        print("No reference data fetched; the pipeline still works without it.")
        return
    zh_text = _fetch(ZH_LOCALE)

    rarity = build_rarity_lookup(texts)
    names = build_name_lookup(texts, zh_text)

    _write("rarity_lookup.json", rarity)
    _write("name_lookup.json", names)


def _write(filename, data):
    out_path = os.path.join(paths.RAW_REFERENCE, filename)
    with open(out_path, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    print("Wrote {} entries to {}".format(len(data), out_path))


if __name__ == "__main__":
    main()
