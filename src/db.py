"""SQL warehouse connection helper.

Uses Databricks SDK default auth — in Databricks Apps that resolves to the
app's service principal (granted CAN_USE on the warehouse via the bundle and
SELECT/MODIFY on the tables via UC grants). Locally it resolves to the CLI
profile.

User attribution for edits is preserved through the audit table's `changed_by`
column, populated from the `X-Forwarded-Email` header at the app layer.

Note: we do NOT use the on-behalf-of-user token (`X-Forwarded-Access-Token`)
for SQL warehouse calls. The default Apps OBO scopes are IAM-only, so the
OBO token gets rejected by the warehouse. To regain UC-level user
attribution, the workspace's OAuth app integration would need to expose the
`sql` scope.
"""
from __future__ import annotations

import logging
import os

from databricks import sql
from databricks.sdk.core import Config

log = logging.getLogger(__name__)


def _hostname() -> str:
    host = os.environ.get("DATABRICKS_HOST") or Config().host
    return host.replace("https://", "").replace("http://", "").rstrip("/")


def _http_path(warehouse_id: str) -> str:
    return f"/sql/1.0/warehouses/{warehouse_id}"


def get_connection():
    """Open a SQL warehouse connection using SDK default auth."""
    warehouse_id = os.environ["WAREHOUSE_ID"]
    headers = Config().authenticate()
    token = headers["Authorization"].split(" ", 1)[1]
    return sql.connect(
        server_hostname=_hostname(),
        http_path=_http_path(warehouse_id),
        access_token=token,
    )
