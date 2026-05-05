"""User identity + OBO token from Databricks Apps request headers."""
from __future__ import annotations

import logging
from typing import Optional

import streamlit as st

log = logging.getLogger(__name__)


def _headers() -> dict:
    try:
        return dict(st.context.headers)
    except Exception:
        return {}


def get_user_email() -> Optional[str]:
    """Return the email Databricks Apps injected, or None when running locally."""
    return _headers().get("X-Forwarded-Email")


def is_local() -> bool:
    return get_user_email() is None
