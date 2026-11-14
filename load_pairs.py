"""One-off script: load pairs.csv (or pairs.xlsx) into the Supabase `pairs` table.

Run from the folder that holds pairs.csv and .streamlit/secrets.toml:
    python load_pairs.py

Safe to re-run: rows are upserted by pair_id, so nothing is duplicated.
"""
import os
import sys
from pathlib import Path

import pandas as pd
from supabase import create_client

BATCH = 500  # rows per request; keeps each HTTP call small


def get_credentials():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if url and key:
        return url, key
    secrets = Path(".streamlit/secrets.toml")
    if secrets.exists():
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # older Python: pip install tomli
        data = tomllib.loads(secrets.read_text())
        return data["SUPABASE_URL"], data["SUPABASE_KEY"]
    sys.exit("No credentials: set SUPABASE_URL/SUPABASE_KEY or create .streamlit/secrets.toml")


def read_pairs() -> pd.DataFrame:
    if Path("pairs.csv").exists():
        df = pd.read_csv("pairs.csv")
    elif Path("pairs.xlsx").exists():
        df = pd.read_excel("pairs.xlsx")
    else:
        sys.exit("Put pairs.csv or pairs.xlsx next to this script.")
    df.columns = [str(c).strip() for c in df.columns]
    missing = {"Pair_ID", "Sentence_1", "Sentence_2"} - set(df.columns)
    if missing:
        sys.exit(f"Missing columns: {missing}. Found: {list(df.columns)}")
    df = df.dropna(subset=["Sentence_1", "Sentence_2"]).reset_index(drop=True)
    df["Pair_ID"] = df["Pair_ID"].astype(str).str.strip()
    if df["Pair_ID"].duplicated().any():
        dupes = df.loc[df["Pair_ID"].duplicated(), "Pair_ID"].tolist()[:5]
        sys.exit(f"Pair_ID must be unique. Duplicates include: {dupes}")
    return df


def main():
    df = read_pairs()
    records = [
        {
            "pair_id": row.Pair_ID,
            "sentence_1": str(row.Sentence_1),
            "sentence_2": str(row.Sentence_2),
            "position": i,  # keeps the order of your file
        }
        for i, row in enumerate(df.itertuples(index=False), start=1)
    ]
    url, key = get_credentials()
    sb = create_client(url, key)
    for start in range(0, len(records), BATCH):
        sb.table("pairs").upsert(records[start:start + BATCH], on_conflict="pair_id").execute()
        print(f"loaded {min(start + BATCH, len(records))}/{len(records)}")
    print("Done.")


if __name__ == "__main__":
    main()
