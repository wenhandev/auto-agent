"""Centralised masking for credential field reads and trace persistence."""

from __future__ import annotations

import re


def mask_card_number(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    if len(digits) < 4:
        return "****"
    return f"**** **** **** {digits[-4:]}"


def mask_secret(value: str) -> str:
    if not value:
        return "***"
    return "***"


def mask_generic(value: str) -> str:
    if not value:
        return "***"
    tail = value[-2:] if len(value) >= 2 else value
    return f"***{tail}"


def mask_field(
    field_name: str,
    value: str,
    *,
    credential_type: str = "generic",
) -> str:
    """Return a masked representation of *value* for API reads and traces."""
    name = field_name.lower()
    ctype = (credential_type or "generic").lower()

    if ctype == "totp" and name in ("secret", "totp_secret"):
        return mask_secret(value)
    if name in ("secret", "totp_secret", "password", "cvc", "api_key", "token"):
        return mask_secret(value)
    if ctype == "credit_card" and name == "number":
        return mask_card_number(value)
    if name == "number" and ctype == "credit_card":
        return mask_card_number(value)
    return mask_generic(value)


def mask_fields(
    fields: dict[str, str],
    *,
    credential_type: str = "generic",
) -> dict[str, str]:
    return {
        k: mask_field(k, v, credential_type=credential_type)
        for k, v in fields.items()
    }


__all__ = [
    "mask_card_number",
    "mask_field",
    "mask_fields",
    "mask_generic",
    "mask_secret",
]
