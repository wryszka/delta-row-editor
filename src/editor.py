"""Diff + write logic: pandas DataFrame -> MERGE + audit INSERTs.

Optimistic concurrency: each MERGE checks `target.updated_at = source.original_updated_at`.
If a row no longer matches (someone else edited concurrently), the MERGE updates
zero rows and we raise ConcurrencyError listing the affected PKs.

Note on transactionality: Databricks SQL does not support multi-statement
transactions. MERGEs are applied row-by-row, then audit rows are inserted.
If the audit INSERT fails after MERGEs succeed, this function raises and the
caller surfaces the partial state.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from .audit import audit_insert_sql, to_audit_param_rows

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")
_UPDATED_AT = "updated_at"


class ConcurrencyError(RuntimeError):
    """Raised when one or more rows failed the optimistic concurrency check."""

    def __init__(self, failed_pks: List[str]):
        super().__init__(
            f"{len(failed_pks)} row(s) were edited by someone else since you loaded "
            f"the table. Refresh and retry. PKs: {failed_pks}"
        )
        self.failed_pks = failed_pks


def _py(v: Any) -> Any:
    """Convert pandas/numpy scalar to a plain Python type for the SQL connector."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v


def _values_equal(a: Any, b: Any) -> bool:
    a_na = a is None or (isinstance(a, float) and pd.isna(a))
    b_na = b is None or (isinstance(b, float) and pd.isna(b))
    if a_na and b_na:
        return True
    if a_na or b_na:
        return False
    return a == b


def compute_diff(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    pk_column: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return {row_changes, audit_records} or empty lists when nothing changed."""
    if list(original.columns) != list(edited.columns):
        raise ValueError("Edited DataFrame columns differ from original")
    if _UPDATED_AT not in original.columns:
        raise ValueError(f"Target table must have an `{_UPDATED_AT}` column")

    orig_idx = original.set_index(pk_column)
    edit_idx = edited.set_index(pk_column)

    row_changes: List[Dict[str, Any]] = []
    audit_records: List[Dict[str, Any]] = []

    for pk in orig_idx.index.intersection(edit_idx.index):
        orig_row = orig_idx.loc[pk]
        edit_row = edit_idx.loc[pk]
        set_values: Dict[str, Any] = {}
        for col in original.columns:
            if col == pk_column or col == _UPDATED_AT:
                continue
            old, new = orig_row[col], edit_row[col]
            if _values_equal(old, new):
                continue
            set_values[col] = _py(new)
            audit_records.append(
                {
                    "pk_value": pk,
                    "column": col,
                    "old_value": _py(old),
                    "new_value": _py(new),
                }
            )
        if set_values:
            row_changes.append(
                {
                    "pk_value": _py(pk),
                    "original_updated_at": _py(orig_row[_UPDATED_AT]),
                    "set_values": set_values,
                }
            )

    return {"row_changes": row_changes, "audit_records": audit_records}


def _build_merge_sql(target: str, pk_column: str, set_columns: List[str]) -> str:
    if not _IDENT_RE.match(pk_column):
        raise ValueError(f"Invalid pk column: {pk_column}")
    for c in set_columns:
        if not _IDENT_RE.match(c):
            raise ValueError(f"Invalid column name: {c}")
    set_clauses = [f"`{c}` = %({c})s" for c in set_columns]
    set_clauses.append("updated_at = current_timestamp()")
    return (
        f"MERGE INTO {target} AS t\n"
        "USING (SELECT %(__pk)s AS pk, %(__orig_uat)s AS original_updated_at) AS s\n"
        f"ON t.`{pk_column}` = s.pk\n"
        "WHEN MATCHED AND t.updated_at = s.original_updated_at "
        f"THEN UPDATE SET {', '.join(set_clauses)}"
    )


def save(
    connection,
    target_table: str,
    audit_table: str,
    pk_column: str,
    diff: Dict[str, List[Dict[str, Any]]],
    user_email: str,
) -> Dict[str, int]:
    """Apply MERGEs and audit INSERTs. Returns counts. Raises on conflict/failure."""
    row_changes = diff["row_changes"]
    audit_records = diff["audit_records"]
    if not row_changes:
        return {"rows_merged": 0, "audit_rows": 0}

    rows_merged = 0
    failed_pks: List[str] = []

    with connection.cursor() as cur:
        for row in row_changes:
            set_cols = list(row["set_values"].keys())
            sql_text = _build_merge_sql(target_table, pk_column, set_cols)
            params: Dict[str, Any] = {
                "__pk": row["pk_value"],
                "__orig_uat": row["original_updated_at"],
                **row["set_values"],
            }
            cur.execute(sql_text, params)
            affected = cur.rowcount if cur.rowcount is not None else -1
            if affected == 1:
                rows_merged += 1
            else:
                failed_pks.append(str(row["pk_value"]))

        if failed_pks:
            raise ConcurrencyError(failed_pks)

        audit_param_rows = to_audit_param_rows(audit_records, user_email)
        audit_inserted = 0
        if audit_param_rows:
            audit_sql = audit_insert_sql(audit_table)
            for r in audit_param_rows:
                cur.execute(audit_sql, r)
                audit_inserted += 1

    return {"rows_merged": rows_merged, "audit_rows": audit_inserted}
