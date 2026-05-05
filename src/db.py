"""SQL warehouse connection helper.

Uses the on-behalf-of-user OAuth token when running on Databricks Apps so
edits are attributed to the real user in Unity Catalog audit logs. Falls
back to SDK default auth (CLI profile, env vars) when running locally.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from databricks import sql
from databricks.sdk.core import Config

log = logging.getLogger(__name__)


def _hostname() -> str:
    host = os.environ.get("DATABRICKS_HOST") or Config().host
    return host.replace("https://", "").replace("http://", "").rstrip("/")


def _http_path(warehouse_id: str) -> str:
    return f"/sql/1.0/warehouses/{warehouse_id}"


def get_connection(token: Optional[str]):
    """Open a SQL warehouse connection. If token is None, fall back to SDK auth."""
    warehouse_id = os.environ["WAREHOUSE_ID"]
    if token is None:
        log.warning("No OBO token; falling back to SDK default auth (local dev)")
        token = Config().authenticate()["Authorization"].split(" ", 1)[1]
    return sql.connect(
        server_hostname=_hostname(),
        http_path=_http_path(warehouse_id),
        access_token=token,
    )
