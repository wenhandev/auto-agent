from __future__ import annotations

from app.integrations.credential_types import register_credential_type
from app.integrations.google_oauth import GOOGLE_SHEETS_OAUTH2_TYPE


def register() -> None:
    register_credential_type(GOOGLE_SHEETS_OAUTH2_TYPE)


__all__ = ["GOOGLE_SHEETS_OAUTH2_TYPE", "register"]
