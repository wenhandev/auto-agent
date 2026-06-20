"""Minimal TOTP code generation for login / vision flows and interpolation.

Credential kinds, masking, and ``{{totp.*}}`` tokens are wired through
:cmod:`app.services.credential_masking` and :mod:`app.services.variable_interpolation`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.crypto import decrypt
from app.db.models import Credential, WorkflowCredential
from app.services.credential_interpolation import CredentialResolutionError

# Re-request the code when fewer than this many seconds remain in the period.
REFRESH_WINDOW_SECONDS = 5

# Documented skew tolerance (±1 step) for sites with clock drift.
SKEW_STEPS = 1


class TotpNotAvailable(ValueError):
    """Raised when no TOTP secret can be resolved for the identifier."""


def _base32_decode(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def current_code(
    secret: str,
    *,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "sha1",
    for_time: Optional[int] = None,
    step_offset: int = 0,
) -> str:
    """Compute the RFC 6238 TOTP code for *secret* (base32)."""
    if for_time is None:
        for_time = int(time.time())
    counter = int(for_time) // period + step_offset
    digestmod = getattr(hashlib, algorithm.lower(), hashlib.sha1)
    key = _base32_decode(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, digestmod).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def seconds_until_rollover(*, period: int = 30, for_time: Optional[int] = None) -> int:
    """Seconds remaining before the current TOTP step rolls over."""
    if for_time is None:
        for_time = int(time.time())
    return period - (int(for_time) % period)


def should_refresh_code(*, period: int = 30, for_time: Optional[int] = None) -> bool:
    """True when the live code is near rollover and should be re-fetched."""
    return seconds_until_rollover(period=period, for_time=for_time) <= REFRESH_WINDOW_SECONDS


def codes_with_skew(
    secret: str,
    *,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "sha1",
    for_time: Optional[int] = None,
    skew_steps: int = SKEW_STEPS,
) -> list[str]:
    """Return codes for offsets ``[-skew_steps, …, +skew_steps]`` (deduped)."""
    seen: set[str] = set()
    out: list[str] = []
    for offset in range(-skew_steps, skew_steps + 1):
        code = current_code(
            secret,
            digits=digits,
            period=period,
            algorithm=algorithm,
            for_time=for_time,
            step_offset=offset,
        )
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _linked_credential_ids(workflow_id: str, session: Session) -> set[str]:
    rows = session.exec(
        select(WorkflowCredential.credential_id).where(
            WorkflowCredential.workflow_id == workflow_id
        )
    ).all()
    return {r for r in rows}


def _load_credential_fields(
    name: str,
    session: Session,
    *,
    workflow_id: Optional[str],
) -> dict[str, str]:
    cred = session.exec(select(Credential).where(Credential.name == name)).first()
    if cred is None:
        raise CredentialResolutionError(f"unknown credential {name!r}")
    if workflow_id is not None:
        allowed = _linked_credential_ids(workflow_id, session)
        if cred.id not in allowed:
            raise CredentialResolutionError(
                f"credential {name!r} is not linked to this workflow"
            )
    try:
        plaintext = decrypt(cred.ciphertext)
        data = __import__("json").loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise CredentialResolutionError(
            f"credential {name!r}: decryption failed"
        ) from exc
    if not isinstance(data, dict):
        raise CredentialResolutionError(f"credential {name!r}: invalid stored blob")
    return {str(k): str(v) for k, v in data.items()}


def _totp_params(fields: dict[str, str]) -> dict[str, Any]:
    secret = fields.get("totp_secret") or fields.get("secret")
    if not secret:
        raise TotpNotAvailable(
            f"credential has no totp_secret field"
        )
    return {
        "secret": secret,
        "digits": int(fields.get("digits") or 6),
        "period": int(fields.get("period") or 30),
        "algorithm": str(fields.get("algorithm") or "sha1"),
    }


def resolve_totp_code(
    identifier: str,
    session: Session,
    *,
    workflow_id: Optional[str],
    for_time: Optional[int] = None,
    refresh_if_stale: bool = True,
) -> str:
    """Return the live TOTP code for a linked credential *identifier*."""
    fields = _load_credential_fields(identifier, session, workflow_id=workflow_id)
    params = _totp_params(fields)
    if refresh_if_stale and should_refresh_code(
        period=params["period"], for_time=for_time
    ):
        # Near rollover: wait for the next step so the typed code stays valid.
        wait_s = seconds_until_rollover(period=params["period"], for_time=for_time)
        if wait_s > 0 and wait_s <= REFRESH_WINDOW_SECONDS:
            time.sleep(wait_s + 0.1)
            for_time = int(time.time())
    return current_code(
        params["secret"],
        digits=params["digits"],
        period=params["period"],
        algorithm=params["algorithm"],
        for_time=for_time,
    )


def resolve_card_field(
    name: str,
    field: str,
    session: Session,
    *,
    workflow_id: Optional[str],
) -> str:
    """Return a decrypted card field for interpolation / page fill."""
    fields = _load_credential_fields(name, session, workflow_id=workflow_id)
    if field not in fields:
        raise CredentialResolutionError(
            f"credential {name!r} has no field {field!r}"
        )
    return str(fields[field])


__all__ = [
    "REFRESH_WINDOW_SECONDS",
    "SKEW_STEPS",
    "TotpNotAvailable",
    "codes_with_skew",
    "current_code",
    "resolve_card_field",
    "resolve_totp_code",
    "seconds_until_rollover",
    "should_refresh_code",
]
