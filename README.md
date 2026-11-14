# Sentence pair annotation (Streamlit + Supabase)

Three judges label the same pairs; every answer is saved in Supabase.

## Quick start
1. Create a Supabase project, then run `schema.sql` in Dashboard > SQL Editor.
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.
3. Create and activate a virtual environment, then `pip install -r requirements.txt`.
   - Windows (PowerShell): `py -m venv .venv` then `.venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
4. Put `pairs.csv` (columns Pair_ID, Sentence_1, Sentence_2) in this folder, run `python load_pairs.py`.
5. `python -m streamlit run app.py`

## Files
- `app.py`: the annotation app
- `load_pairs.py`: one-off loader, pairs.csv to the `pairs` table (safe to re-run)
- `schema.sql`: tables, constraints and row level security
- `.streamlit/secrets.toml`: your credentials (never commit)
