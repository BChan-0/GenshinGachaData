"""Shared filesystem paths for the GenshinGachaData scripts.

Every path is computed from this file's location, so the scripts run correctly
no matter what directory you launch them from (the scripts/ folder, the repo
root, anywhere). Import the constants you need instead of hardcoding "../".
"""
import os

# scripts/ -> repo root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

RAW = os.path.join(ROOT, "raw")
RAW_PAIMON = os.path.join(RAW, "paimon")
RAW_UIGF = os.path.join(RAW, "uigf")
RAW_REFERENCE = os.path.join(RAW, "reference")

CSV = os.path.join(ROOT, "csv")
CSV_AGG = os.path.join(CSV, "aggregate")

DB_DIR = os.path.join(ROOT, "database")
DB = os.path.join(DB_DIR, "genshin.db")


def ensure_dirs(*dirs):
    """Create each directory if it does not already exist."""
    for d in dirs:
        os.makedirs(d, exist_ok=True)
