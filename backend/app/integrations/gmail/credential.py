from __future__ import annotations

from app.integrations.credential_types import register_credential_type
from app.integrations.google_oauth import GMAIL_OAUTH2_TYPE


def register() -> None:
    register_credential_type(GMAIL_OAUTH2_TYPE)


__all__ = ["GMAIL_OAUTH2_TYPE", "register"]
