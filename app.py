import hmac
import io
import os
import time

import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="Sentence Pair Annotation", layout="centered")

JUDGES = ["User 1", "User 2", "User 3"]
PAGE = 1000  # Supabase returns at most 1000 rows per request by default


# ---------------------------------------------------------------- connection
def get_secret(name: str, default=None):
    """Look in Streamlit secrets first (secrets.toml, or the Cloud dashboard),
    then in environment variables. The same app runs locally and when deployed."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # no secrets file at all
        pass
    return os.environ.get(name, default)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing SUPABASE_URL / SUPABASE_KEY. Put them in .streamlit/secrets.toml or set them as environment variables.")
    st.stop()


# One shared client is fine HERE: it uses the app's own secret key and nobody
# logs in through it. (If users logged in through the client, it must be per session.)
@st.cache_resource
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


sb = get_client()


def fetch_all(table: str, columns: str, order_by: str, **filters) -> list[dict]:
    """Read every matching row, one page at a time (never silently stops at 1000)."""
    rows, start = [], 0
    while True:
        q = sb.table(table).select(columns).order(order_by).range(start, start + PAGE - 1)
        for col, val in filters.items():
            q = q.eq(col, val)
        batch = q.execute().data
        rows += batch
        if len(batch) < PAGE:
            return rows
        start += PAGE


# ---------------------------------------------------------------- data access
@st.cache_data(ttl=600)
def load_pairs() -> pd.DataFrame:
    """Pairs never change during labeling, so cache them for 10 minutes."""
    rows = fetch_all("pairs", "pair_id,sentence_1,sentence_2", "position")
    df = pd.DataFrame(rows, columns=["pair_id", "sentence_1", "sentence_2"])
    return df.rename(columns={"pair_id": "Pair_ID", "sentence_1": "Sentence_1", "sentence_2": "Sentence_2"})


def load_user_history(user: str) -> pd.DataFrame:
    """NOT cached on purpose: it must be fresh after every save."""
    rows = fetch_all("annotations", "pair_id,time_spent_seconds", "id", user_id=user)
    return pd.DataFrame(rows, columns=["pair_id", "time_spent_seconds"])


def save_annotation(record: dict) -> None:
    # unique(user_id, pair_id) + ignore_duplicates: a double-click cannot create a second row.
    sb.table("annotations").upsert(record, on_conflict="user_id,pair_id", ignore_duplicates=True).execute()


def format_duration(seconds: float) -> str:
    sec = int(round(seconds))
    mins, rem = divmod(sec, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}h {mins}m {rem}s"
    return f"{mins}m {rem}s"


pairs_df = load_pairs()
if pairs_df.empty:
    st.error("The `pairs` table is empty. Run `python load_pairs.py` first.")
    st.stop()

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Annotator Profile")
selected_user = st.sidebar.selectbox("Select Judge / User", JUDGES)

if st.session_state.get("active_user") != selected_user:
    st.session_state["active_user"] = selected_user
    st.session_state["question_start_time"] = time.time()

history = load_user_history(selected_user)
completed_ids = set(history["pair_id"].astype(str))
cumulative_seconds = float(history["time_spent_seconds"].astype(float).sum()) if not history.empty else 0.0

st.sidebar.metric("Completed Pairs", f"{len(completed_ids)} / {len(pairs_df)}")
st.sidebar.metric("Total Recorded Time", format_duration(cumulative_seconds))

# Judges must not see each other's answers, so the export is behind an admin password.
admin_pw = get_secret("ADMIN_PASSWORD")
if admin_pw:
    st.sidebar.divider()
    with st.sidebar.expander("Admin export"):
        entered = st.text_input("Admin password", type="password")
        if entered and hmac.compare_digest(entered, str(admin_pw)):
            everything = pd.DataFrame(fetch_all(
                "annotations",
                "created_at,user_id,pair_id,same_meaning,diversity_score,time_spent_seconds",
                "id",
            ))
            buf = io.BytesIO()
            everything.to_excel(buf, index=False)
            st.download_button(
                "Download all results (xlsx)",
                data=buf.getvalue(),
                file_name="results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        elif entered:
            st.error("Wrong password.")

# ---------------------------------------------------------------- main area
st.title("Sentence Pair Evaluation")

remaining_df = pairs_df[~pairs_df["Pair_ID"].isin(completed_ids)].reset_index(drop=True)

if remaining_df.empty:
    st.success(f"All {len(pairs_df)} pairs are completed for **{selected_user}**!")
    st.info(f"Total time recorded: **{format_duration(cumulative_seconds)}**. All answers are saved in Supabase.")
    st.stop()

current_row = remaining_df.iloc[0]
pair_id = str(current_row["Pair_ID"])

if st.session_state.get("current_pair_id") != pair_id:
    st.session_state["current_pair_id"] = pair_id
    st.session_state["question_start_time"] = time.time()

st.progress(len(completed_ids) / len(pairs_df))
st.caption(f"Currently judging as **{selected_user}** | Pair ID: **{pair_id}** ({len(completed_ids) + 1} of {len(pairs_df)})")

st.markdown("### Sentence 1")
st.info(current_row["Sentence_1"])

st.markdown("### Sentence 2")
st.info(current_row["Sentence_2"])

with st.form(key=f"form_{selected_user}_{pair_id}", clear_on_submit=True):
    same_meaning = st.radio(
        "1. Do these two sentences have the same meaning?",
        options=["True", "False"],
        horizontal=True,
        index=None,
    )

    diversity_score = st.radio(
        "2. Rate the diversity between the two sentences (1 = Very Low, 5 = Very High)",
        options=[1, 2, 3, 4, 5],
        horizontal=True,
        index=None,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        submitted = st.form_submit_button("Save & Next Pair", type="primary", use_container_width=True)
    with col2:
        reset_timer = st.form_submit_button("Reset Pair Timer", use_container_width=True)

    if reset_timer:
        st.session_state["question_start_time"] = time.time()
        st.toast("Timer for this pair restarted from 0s.")

    if submitted:
        if same_meaning is None or diversity_score is None:
            st.warning("Please answer both questions before saving.")
        else:
            elapsed = round(time.time() - st.session_state["question_start_time"], 2)
            record = {
                "user_id": selected_user,
                "pair_id": pair_id,
                "same_meaning": same_meaning == "True",   # the database stores a real boolean
                "diversity_score": int(diversity_score),
                "time_spent_seconds": elapsed,
                # created_at is filled in by the database
            }
            try:
                save_annotation(record)
            except Exception as e:  # network or database error: keep the judge on this pair
                st.error(f"Could not save, please try again. ({e})")
            else:
                st.session_state["question_start_time"] = time.time()
                st.rerun()
