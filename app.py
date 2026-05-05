"""Streamlit UI for end-user row editing of a Delta table."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import streamlit as st

from src.auth import get_user_email, is_local
from src.db import get_connection
from src.editor import compute_diff, save

logging.basicConfig(level=logging.INFO)

TARGET_TABLE = os.environ["TARGET_TABLE"]
AUDIT_TABLE = os.environ["AUDIT_TABLE"]
PK_COLUMN = os.environ["PK_COLUMN"]

st.set_page_config(page_title="Delta Row Editor", layout="wide")


def load_data() -> pd.DataFrame:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {TARGET_TABLE} ORDER BY {PK_COLUMN}")
            return cur.fetchall_arrow().to_pandas()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _refresh_state() -> None:
    st.session_state.original_df = load_data()
    st.session_state.refreshed_at = _now_iso()
    st.session_state.editor_nonce = st.session_state.get("editor_nonce", 0) + 1


def main() -> None:
    st.title("Delta Row Editor")
    st.caption(
        "About this demo — sample app demonstrating end-user row editing of a "
        "Delta table on Databricks Apps. Uses Streamlit + databricks-sql-connector. "
        "Edits are attributed to the signed-in user via on-behalf-of-user OAuth."
    )

    user_email = get_user_email()
    user_label = user_email or "(local dev)"

    if is_local():
        st.warning(
            "Running locally — using SDK default auth. Edits will not be attributed "
            "to a real Databricks user."
        )

    cols = st.columns([1, 1, 2])
    cols[0].metric("Target", TARGET_TABLE.split(".")[-1])
    cols[1].metric("User", user_label)
    refresh_clicked = cols[2].button("Refresh from source")

    error_slot = st.empty()

    if "original_df" not in st.session_state or refresh_clicked:
        try:
            _refresh_state()
        except Exception as e:
            error_slot.error(f"Failed to load table: {e}")
            return

    df: pd.DataFrame = st.session_state.original_df

    info_cols = st.columns([1, 1])
    info_cols[0].metric("Rows", len(df))
    info_cols[1].metric("Last refresh", st.session_state.refreshed_at)

    disabled_cols = [PK_COLUMN]
    if "updated_at" in df.columns:
        disabled_cols.append("updated_at")

    edited = st.data_editor(
        df,
        disabled=disabled_cols,
        num_rows="fixed",
        use_container_width=True,
        key=f"editor_{st.session_state.editor_nonce}",
    )

    try:
        diff = compute_diff(df, edited, PK_COLUMN)
    except Exception as e:
        error_slot.error(f"Diff failed: {e}")
        return

    audit_records = diff["audit_records"]
    if not audit_records:
        st.info("No changes pending.")
        return

    st.subheader(f"Pending changes ({len(audit_records)} cell edits)")
    preview = pd.DataFrame(audit_records).rename(
        columns={
            "pk_value": PK_COLUMN,
            "column": "column",
            "old_value": "old",
            "new_value": "new",
        }
    )
    st.dataframe(preview, use_container_width=True)

    if st.button("Save changes", type="primary"):
        try:
            with get_connection() as conn:
                result = save(
                    conn,
                    TARGET_TABLE,
                    AUDIT_TABLE,
                    PK_COLUMN,
                    diff,
                    user_email=user_email or "(local dev)",
                )
            st.success(
                f"Saved {result['rows_merged']} row(s); wrote "
                f"{result['audit_rows']} audit record(s)."
            )
            _refresh_state()
            st.rerun()
        except Exception as e:
            error_slot.error(f"Save failed: {e}")


if __name__ == "__main__":
    main()
