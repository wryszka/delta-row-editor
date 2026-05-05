"""Audit-row helpers: package per-column change records for INSERT."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


def to_audit_param_rows(
    audit_records: Iterable[Dict[str, Any]],
    user_email: str,
) -> List[Dict[str, Any]]:
    """Shape diff audit records for the parameterized INSERT in editor.save()."""
    return [
        {
            "pk_value": str(r["pk_value"]),
            "column_name": r["column"],
            "old_value": None if r["old_value"] is None else str(r["old_value"]),
            "new_value": None if r["new_value"] is None else str(r["new_value"]),
            "changed_by": user_email,
        }
        for r in audit_records
    ]


def audit_insert_sql(audit_table: str) -> str:
    return (
        f"INSERT INTO {audit_table} "
        "(pk_value, column_name, old_value, new_value, changed_by, changed_at) "
        "VALUES (%(pk_value)s, %(column_name)s, %(old_value)s, %(new_value)s, "
        "%(changed_by)s, current_timestamp())"
    )
