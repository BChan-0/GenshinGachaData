# -*- coding: utf-8 -*-
# NOTE: run with python3 (this repo needs pandas/PyGithub, installed for python3).
"""Collect INDIVIDUAL wish histories in UIGF format into raw/uigf/.

UIGF (Uniformed Interchangeable GachaLog Format, https://uigf.org) is the
community standard for exported per-pull wish histories. Unlike paimon.moe's
aggregate stats, these are real per-player pull logs -- the source for the
individual dataset (date/time/region/result/rarity/pity/banner per pull).

Three ways data lands in raw/uigf/, in increasing effort:
  1. A bundled synthetic sample (sample_uigf.json) so the pipeline runs with
     zero setup -- nothing to do here, it already ships in the repo.
  2. Files YOU drop into raw/uigf/ (your own export, or ones you downloaded).
  3. This script's best-effort GitHub code search, which needs a token.

GitHub *code* search (searching file contents) requires authentication. Set a
token in the GITHUB_TOKEN (or GH_TOKEN) environment variable. Without one, this
script prints how to enable it and exits cleanly -- parse_uigf.py still works on
whatever files are already in raw/uigf/.

Search notes (GitHub legacy /search/code endpoint, which PyGithub<2.0 uses):
  * Each query must carry a free-text term (or be filename-only); only legacy
    qualifiers are valid (extension:, filename:, path:, in:). No NOT/AND/OR,
    no regex, no path globs -- those silently fail or 422.
  * Hard ceiling of 1000 results per query; code search is rate-limited to
    ~10 requests/minute, so we throttle and bound pagination.
  * Many hits for UIGF keys are JSON *schema* files, not real exports -- we
    filter those out in _looks_like_uigf() rather than in the query.
The query set targets export_app strings of known UIGF exporter tools (Snap
Hutao, genshin-wish-export, etc.) plus structural signatures, which are the
most reliable needles for real committed exports.
"""
import json
import os
import time

import paths

# --- search configuration ---------------------------------------------------

# Best-first. Multi-word export_app values are split into two ANDed quoted
# terms (more robust than one ":"-spaced phrase). All legacy-endpoint valid.
SEARCH_QUERIES = [
    '"export_app" "Snap Hutao" "uigf_gacha_type" extension:json',
    '"hk4e" "uigf_gacha_type" "export_app" extension:json',
    '"uigf_version" "region_time_zone" "uigf_gacha_type" extension:json',
    '"export_app" "genshin-wish-export" "uigf_gacha_type" extension:json',
    '"export_app" "胡桃" "uigf_version" extension:json',
    '"export_app" "小黑盒" "region_time_zone" extension:json',
    '"export_app" "genshin-gacha-export" "uigf_version" extension:json',
    '"export_app" "paimon.moe" "uigf_gacha_type" extension:json',
    '"export_app" "Paimon.moe-WishHistory-UIGF-Exporter" extension:json',
    '"uigf_gacha_type" "rank_type" "item_id" "export_app" extension:json',
    '"uigf_gacha_type" "rank_type" filename:UIGF.json',
    '"uigf_gacha_type" "rank_type" path:gacha.json',
]

# Known repositories to harvest IN FULL (every UIGF export, not just search
# hits). This is the highest-yield lever: code search only returns a capped,
# relevance-ranked subset per repo, but an aggregator repo can hold hundreds of
# exports. Add "owner/repo" entries here -- e.g. repos you found in the search
# results (each saved file is named "owner__repo__sha__path"). The git-tree +
# blob API used here also bypasses code search's 384 KB file-size cap.
# NOTE: do NOT add Erlonealpha/generat_genshin_gahca_data -- that repo
# *generates synthetic* UIGF data, which would pollute the dataset with fake
# players. Only add repos with real, voluntarily-exported wish histories.
REPOS = [
    "Terabinaryte/blog",
    "Grymoira/Grimoire",
]

GITHUB_SEARCH_CEILING = 1000   # GitHub serves at most 1000 results per query
MAX_RESULTS_PER_QUERY = 1000    # per-query budget; raise toward 1000 if desired
PER_PAGE = 100                 # max page size -> fewer page fetches
SEARCH_SLEEP = 7.0             # seconds between search requests (~10/min limit)
BLOB_SLEEP = 0.1               # small pause between blob fetches (core limit)


def get_token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def main():
    paths.ensure_dirs(paths.RAW_UIGF)

    token = get_token()
    if not token:
        print(
            "No GITHUB_TOKEN set -- skipping the GitHub search.\n"
            "  * The pipeline still works: parse_uigf.py reads the bundled\n"
            "    sample and any .json files you place in {}.\n"
            "  * To enable scraping, create a GitHub personal access token\n"
            "    (classic, no scopes needed for public search) and run:\n"
            "        export GITHUB_TOKEN=ghp_your_token_here"
            .format(paths.RAW_UIGF))
        return

    try:
        from github import Github
        from github.GithubException import (
            BadCredentialsException, GithubException,
            RateLimitExceededException, UnknownObjectException,
        )
    except ImportError:
        raise SystemExit(
            "PyGithub is required for the GitHub search. Install it with:\n"
            "    pip install 'PyGithub<2.0'")

    exc_types = {
        "rate": RateLimitExceededException,
        "github": GithubException,
        "creds": BadCredentialsException,
        "unknown": UnknownObjectException,
    }

    gh = Github(token, per_page=PER_PAGE)
    seen_keys = set()    # repo/path -- cheap, available on the hit (no API call)
    seen_shas = set()    # blob sha -- catches the same file vendored elsewhere
    downloaded = 0

    cap = min(MAX_RESULTS_PER_QUERY, GITHUB_SEARCH_CEILING)

    for q_index, query in enumerate(SEARCH_QUERIES):
        if q_index:
            time.sleep(SEARCH_SLEEP)  # one search request per query
        print("Searching:", query)

        try:
            results = gh.search_code(query)
        except exc_types["creds"]:
            raise SystemExit(
                "GitHub rejected the token (401). It is missing or expired -- "
                "create a fresh PAT and re-export GITHUB_TOKEN.")
        except exc_types["rate"] as exc:
            print("  rate limited; backing off.")
            _sleep_for_reset(exc)
            continue
        except exc_types["github"] as exc:
            print("  query skipped (status {}): {}".format(
                getattr(exc, "status", "?"), _msg(exc)))
            continue
        except Exception as exc:  # raw network errors propagate unwrapped
            print("  search failed ({}); skipping.".format(exc))
            continue

        downloaded += _consume(results, cap, gh, seen_keys, seen_shas, exc_types)

    # Full-repo harvest: pull every UIGF export from each configured repo.
    for repo_name in REPOS:
        print("Harvesting repo:", repo_name)
        downloaded += _harvest_repo(
            gh, repo_name, seen_keys, seen_shas, exc_types)

    print("\nDone. {} UIGF file(s) downloaded into {}.".format(
        downloaded, paths.RAW_UIGF))


def _harvest_repo(gh, repo_name, seen_keys, seen_shas, exc_types):
    """Download every UIGF export in a repo by walking its full file tree."""
    try:
        repo = gh.get_repo(repo_name)
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
    except exc_types["creds"]:
        raise SystemExit("GitHub rejected the token (401) while harvesting.")
    except exc_types["rate"] as exc:
        print("  rate limited; backing off.")
        _sleep_for_reset(exc)
        return 0
    except (exc_types["github"], exc_types["unknown"]) as exc:
        print("  cannot read {} (status {}); skipping.".format(
            repo_name, getattr(exc, "status", "?")))
        return 0
    except Exception as exc:
        print("  harvest failed ({}); skipping.".format(exc))
        return 0

    candidates = [e for e in tree.tree
                  if e.type == "blob" and e.path.lower().endswith(".json")
                  and "schema" not in e.path.lower()]
    print("  {} json file(s) in tree".format(len(candidates)))

    saved = 0
    for entry in candidates:
        key = repo_name + "/" + entry.path
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if entry.sha in seen_shas:
            continue

        time.sleep(BLOB_SLEEP)
        content = _read_blob(repo, entry.sha, exc_types)
        if content is None:
            continue
        try:
            data = json.loads(content)
        except ValueError:
            continue
        if not _looks_like_uigf(data):
            continue

        seen_shas.add(entry.sha)
        if _save_named(repo_name, entry.sha, entry.path, data):
            saved += 1
    print("  saved {} export(s) from {}".format(saved, repo_name))
    return saved


def _read_blob(repo, sha, exc_types):
    """Fetch a git blob by sha (no 384 KB code-search cap), decoded to UTF-8."""
    import base64
    try:
        blob = repo.get_git_blob(sha)
        if blob.encoding == "base64":
            return base64.b64decode(blob.content).decode("utf8")
        return blob.content
    except exc_types["rate"]:
        raise
    except (exc_types["github"], exc_types["unknown"]):
        return None
    except (ValueError, UnicodeDecodeError):
        return None
    except Exception:
        return None


def _consume(results, cap, gh, seen_keys, seen_shas, exc_types):
    """Iterate one query's paginated results, saving real UIGF exports."""
    saved = 0
    i = -1
    it = iter(enumerate(results))
    while True:
        try:
            i, item = next(it)
        except StopIteration:
            break
        except exc_types["rate"] as exc:
            print("  rate limited mid-pagination; backing off.")
            _sleep_for_reset(exc)
            break
        except exc_types["github"] as exc:
            # 422 once we cross the 1000-result wall, or other paging error.
            print("  pagination stopped (status {}).".format(
                getattr(exc, "status", "?")))
            break
        except Exception as exc:
            print("  pagination error ({}); stopping query.".format(exc))
            break

        if i >= cap:
            break
        # A new /search/code page is fetched each time we cross a page boundary.
        if i and i % PER_PAGE == 0:
            time.sleep(SEARCH_SLEEP)

        key = item.repository.full_name + "/" + item.path
        if key in seen_keys:
            continue
        seen_keys.add(key)

        sha = getattr(item, "sha", None)
        if sha and sha in seen_shas:
            continue

        if "schema" in item.path.lower():  # skip schema files before fetching
            continue

        content = _read_content(item, exc_types)
        if content is None:
            continue
        try:
            data = json.loads(content)
        except ValueError:
            continue
        if not _looks_like_uigf(data):
            continue

        if sha:
            seen_shas.add(sha)
        if _save(item, data):
            saved += 1
    return saved


def _read_content(item, exc_types):
    """Return decoded UTF-8 file content, or None if it can't be read.

    Uses item.decoded_content (a single core-API fetch) rather than
    base64-decoding item.content by hand -- search hits arrive without content
    populated, and decoded_content handles the encoding correctly.
    """
    try:
        return item.decoded_content.decode("utf8")
    except exc_types["rate"]:
        raise
    except (exc_types["unknown"], exc_types["github"]):
        return None
    except (AssertionError, AttributeError, UnicodeDecodeError):
        return None
    except Exception:  # raw network errors
        return None


def _save(item, data):
    return _save_named(
        item.repository.full_name, getattr(item, "sha", ""), item.path, data)


def _save_named(repo_full_name, sha, path, data):
    """Write an export as raw/uigf/<repo>__<sha8>__<path>.json (unique name)."""
    safe_repo = repo_full_name.replace("/", "__")
    safe_path = path.replace("/", "__")
    sha8 = (sha or "")[:8]
    name = "{}__{}__{}".format(safe_repo, sha8, safe_path) if sha8 \
        else "{}__{}".format(safe_repo, safe_path)
    out_path = os.path.join(paths.RAW_UIGF, name)
    with open(out_path, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("  saved", os.path.basename(out_path))
    return True


# --- UIGF detection ----------------------------------------------------------

# Top-level keys that mark a JSON *schema* file rather than a real export.
_SCHEMA_MARKERS = ("$schema", "properties", "definitions", "$defs")


def _looks_like_uigf(data):
    """True only for real exports -- rejects JSON-schema files and stubs."""
    if not isinstance(data, dict):
        return False
    if any(marker in data for marker in _SCHEMA_MARKERS):
        return False

    # Flat v2.x / v3.0: {info, list:[{...}]}
    pulls = data.get("list")
    if isinstance(pulls, list) and pulls:
        first = pulls[0]
        if not isinstance(first, dict):
            return False
        has_key = "uigf_gacha_type" in first or "gacha_type" in first
        # Require a populated real value, not just a key (rejects schema stubs).
        has_value = bool(first.get("time")) and bool(
            first.get("item_id") or first.get("name"))
        return has_key and has_value

    # v4.0+: top-level per-game arrays, each with its own pull list.
    for game in ("hk4e", "hkrpg", "nap"):
        block = data.get(game)
        if isinstance(block, list) and any(
                isinstance(acc, dict) and acc.get("list") for acc in block):
            return True
    return False


# --- rate-limit backoff ------------------------------------------------------

def _sleep_for_reset(exc):
    """Sleep until the rate-limit resets, using the response headers."""
    headers = getattr(exc, "headers", None) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        time.sleep(int(retry_after) + 1)
        return
    reset = headers.get("x-ratelimit-reset") or headers.get("X-RateLimit-Reset")
    if reset:
        try:
            time.sleep(max(0, int(reset) - int(time.time())) + 1)
            return
        except ValueError:
            pass
    time.sleep(60)


def _msg(exc):
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        return data.get("message", str(exc))
    return str(exc)


if __name__ == "__main__":
    main()
