from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from sqlmodel import Session, select

from app.db.crypto import decrypt, encrypt
from app.db.models import Credential, WorkflowCredential
from app.integrations.auth import RenderedRequest, inject_auth, resolve_cred_type
from app.integrations.hooks import get_hooks
from app.integrations.json_path import resolve_path
from app.integrations.redaction import redact_request_summary
from app.integrations.registry import resolve_operation
from app.integrations.renderer import render_template
from app.integrations.schema import Operation, Pagination, RequestTemplate
from app.nodes._http_client import request as http_request
from app.nodes.result import Item, NodeResult
from app.services.credential_interpolation import CredentialResolutionError
from app.settings import settings

logger = logging.getLogger(__name__)

_OAUTH_LOCKS: dict[str, asyncio.Lock] = {}
_TOKEN_SKEW_SEC = 60


class IntegrationError(ValueError):
    pass


def _validate_fields(op: Operation, fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in op.fields:
        val = fields.get(spec.name, spec.default)
        if spec.required and (val is None or val == ""):
            raise IntegrationError(f"missing required field {spec.name!r}")
        if val is None:
            continue
        if spec.kind == "number":
            try:
                out[spec.name] = int(val) if isinstance(val, bool) else float(val)
                if float(val).is_integer():
                    out[spec.name] = int(float(val))
            except (TypeError, ValueError) as exc:
                raise IntegrationError(
                    f"field {spec.name!r} must be a number"
                ) from exc
        elif spec.kind == "boolean":
            if isinstance(val, bool):
                out[spec.name] = val
            else:
                out[spec.name] = str(val).lower() in ("1", "true", "yes")
        elif spec.kind == "options" and spec.options:
            allowed = {o.value for o in spec.options}
            if val not in allowed:
                raise IntegrationError(
                    f"field {spec.name!r} must be one of {sorted(allowed)!r}"
                )
            out[spec.name] = val
        else:
            out[spec.name] = val
    return out


def _linked_credential_ids(workflow_id: str, session: Session) -> set[str]:
    rows = session.exec(
        select(WorkflowCredential.credential_id).where(
            WorkflowCredential.workflow_id == workflow_id
        )
    ).all()
    return {r for r in rows}


def _load_credential(
    name: str,
    session: Session,
    *,
    workflow_id: Optional[str],
) -> tuple[Credential, dict[str, str]]:
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
        data = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise CredentialResolutionError(
            f"credential {name!r}: decryption failed"
        ) from exc
    if not isinstance(data, dict):
        raise CredentialResolutionError(f"credential {name!r}: invalid stored blob")
    return cred, {str(k): str(v) for k, v in data.items()}


def _persist_credential_fields(
    cred: Credential, fields: dict[str, str], session: Session
) -> None:
    cred.ciphertext = encrypt(
        json.dumps(fields, ensure_ascii=False).encode("utf-8")
    )
    cred.updated_at = datetime.now(timezone.utc)
    session.add(cred)
    session.commit()


def _oauth_lock(credential_id: str) -> asyncio.Lock:
    if credential_id not in _OAUTH_LOCKS:
        _OAUTH_LOCKS[credential_id] = asyncio.Lock()
    return _OAUTH_LOCKS[credential_id]


def _token_expired(fields: dict[str, str]) -> bool:
    raw = fields.get("expires_at")
    if not raw:
        return False
    try:
        exp = float(raw)
    except ValueError:
        return False
    return time.time() >= exp - _TOKEN_SKEW_SEC


async def _refresh_oauth_token(
    cred: Credential,
    fields: dict[str, str],
    session: Session,
    *,
    transport: Any = None,
) -> str:
    cred_type = resolve_cred_type(cred.type or "generic")
    auth = cred_type.auth
    if auth.strategy != "oauth2" or not auth.token_url:
        raise IntegrationError("credential is not oauth2")

    refresh = fields.get("refresh_token", "")
    if not refresh:
        raise IntegrationError("oauth2 refresh_token missing; reconnect the app")

    client_id = fields.get(auth.client_id_field or "client_id", "")
    client_secret = fields.get(auth.client_secret_field or "client_secret", "")

    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        resp = await client.post(
            auth.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    if resp.status_code >= 400:
        raise IntegrationError(f"oauth2 refresh failed: HTTP {resp.status_code}")
    payload = resp.json()
    token_field = auth.token_field or "access_token"
    access = str(payload.get(token_field, ""))
    if not access:
        raise IntegrationError("oauth2 refresh response missing access_token")
    fields[token_field] = access
    if payload.get("refresh_token"):
        fields["refresh_token"] = str(payload["refresh_token"])
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        fields["expires_at"] = str(time.time() + float(expires_in))
    _persist_credential_fields(cred, fields, session)
    return access


async def _resolve_oauth_access_token(
    cred: Credential,
    fields: dict[str, str],
    session: Session,
    *,
    transport: Any = None,
) -> str:
    cred_type = resolve_cred_type(cred.type or "generic")
    token_field = cred_type.auth.token_field or "access_token"
    if not _token_expired(fields):
        return fields.get(token_field, "")
    lock = _oauth_lock(cred.id)
    async with lock:
        _, fresh = _load_credential(cred.name, session, workflow_id=None)
        if not _token_expired(fresh):
            return fresh.get(token_field, "")
        return await _refresh_oauth_token(
            cred, fresh, session, transport=transport
        )


def _body_kind(body_type: str) -> str:
    if body_type == "form":
        return "form"
    if body_type == "raw":
        return "text"
    return "json"


def _build_rendered_request(
    tmpl: RequestTemplate,
    *,
    fields: dict[str, Any],
    cred_fields: dict[str, str],
    secret_keys: set[str],
    extra_query: dict[str, str] | None = None,
) -> RenderedRequest:
    rendered_url = render_template(
        tmpl.url, fields=fields, cred=cred_fields, secret_keys=secret_keys
    )
    rendered_query = render_template(
        tmpl.query, fields=fields, cred=cred_fields, secret_keys=secret_keys
    )
    rendered_headers = render_template(
        tmpl.headers, fields=fields, cred=cred_fields, secret_keys=secret_keys
    )
    rendered_body = render_template(
        tmpl.body, fields=fields, cred=cred_fields, secret_keys=secret_keys
    )
    query = {str(k): str(v) for k, v in (rendered_query or {}).items()}
    if extra_query:
        query.update({k: str(v) for k, v in extra_query.items()})
    return RenderedRequest(
        method=tmpl.method,
        url=str(rendered_url),
        query=query,
        headers={str(k): str(v) for k, v in (rendered_headers or {}).items()},
        body=rendered_body,
        body_kind=_body_kind(tmpl.body_type),
        secret_keys=secret_keys,
    )


def _append_query(url: str, query: dict[str, str]) -> str:
    if not query:
        return url
    parsed = urlparse(url)
    existing = parse_qs(parsed.query, keep_blank_values=True)
    for k, v in query.items():
        existing[k] = [v]
    flat = [(k, val) for k, vals in existing.items() for val in vals]
    new_query = urlencode(flat)
    return urlunparse(parsed._replace(query=new_query))


def _parse_link_header(headers: dict[str, str], rel: str) -> str | None:
    link = headers.get("link") or headers.get("Link") or ""
    for part in link.split(","):
        section = part.strip().split(";")
        if len(section) < 2:
            continue
        url_part = section[0].strip()
        if not (url_part.startswith("<") and url_part.endswith(">")):
            continue
        url = url_part[1:-1]
        rel_found = None
        for item in section[1:]:
            item = item.strip()
            if item.startswith("rel="):
                rel_found = item.split("=", 1)[1].strip().strip('"')
        if rel_found == rel:
            return url
    return None


def _merge_body_cursor(
    body: Any,
    *,
    param: str,
    cursor: str,
) -> Any:
    if isinstance(body, dict):
        merged = dict(body)
        merged[param] = cursor
        return merged
    return {param: cursor}


def _items_from_response(
    http_out: dict[str, Any], op: Operation
) -> list[dict[str, Any]]:
    payload = http_out.get("json")
    if payload is None:
        ct = (http_out.get("headers") or {}).get("content-type", "")
        if "octet-stream" in ct or "application/pdf" in ct:
            return [{"binary": {"text": http_out.get("text", "")}}]
        raise IntegrationError("response is not JSON and has no binary mapping")

    resp = op.response
    if resp.item_path:
        records = resolve_path(payload, resp.item_path)
        if not isinstance(records, list):
            raise IntegrationError(f"item_path {resp.item_path!r} did not resolve to a list")
        return [r if isinstance(r, dict) else {"value": r} for r in records]
    if resp.root_path:
        obj = resolve_path(payload, resp.root_path) if resp.root_path else payload
        if isinstance(obj, dict):
            return [obj]
        return [{"value": obj}]
    return [payload if isinstance(payload, dict) else {"value": payload}]


def _next_page_query(
    pagination: Pagination,
    http_out: dict[str, Any],
    *,
    page_index: int,
    cursor: str | None,
) -> dict[str, str] | None:
    if pagination.type == "cursor":
        if not cursor:
            return None
        param = pagination.cursor_param or "cursor"
        return {param: cursor}
    if pagination.type == "offset":
        offset_param = pagination.offset_param or "offset"
        limit_param = pagination.limit_param or "limit"
        next_offset = page_index * pagination.page_size
        return {offset_param: str(next_offset), limit_param: str(pagination.page_size)}
    if pagination.type == "link_header":
        nxt = _parse_link_header(http_out.get("headers") or {}, pagination.link_header_rel)
        if not nxt:
            return None
        return {"__next_url__": nxt}
    return None


async def _execute_page(
    req: RenderedRequest,
    *,
    transport: Any,
    timeout_ms: int,
) -> dict[str, Any]:
    url = _append_query(req.url, req.query)
    out = await http_request(
        method=req.method,
        url=url,
        headers=req.headers,
        body=req.body,
        body_kind=req.body_kind,
        timeout_ms=timeout_ms,
        transport=transport,
    )
    status = int(out.get("status", 0))
    if status >= 500:
        raise IntegrationError(
            f"HTTP {status} from provider after retries: {out.get('text', '')[:200]}"
        )
    return out


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
    session: Session | None = None,
    workflow_id: str | None = None,
    transport: Any = None,
) -> list[Item] | NodeResult:
    app = str(params["app"])
    resource = str(params["resource"])
    operation = str(params["operation"])
    raw_fields = params.get("fields") or {}
    if not isinstance(raw_fields, dict):
        raise IntegrationError("fields must be an object")
    credential_name = params.get("credential")

    _, _, op = resolve_operation(app, resource, operation)
    fields = _validate_fields(op, raw_fields)

    cred_fields: dict[str, str] = {}
    cred_row: Credential | None = None
    cred_type_name = "generic"

    if credential_name and session is not None:
        cred_row, cred_fields = _load_credential(
            str(credential_name), session, workflow_id=workflow_id
        )
        cred_type_name = cred_row.type or "generic"
        desc, _, _ = resolve_operation(app, resource, operation)
        if desc.credentials and cred_type_name not in desc.credentials:
            if cred_type_name != "generic":
                raise IntegrationError(
                    f"credential type {cred_type_name!r} is not valid for app {app!r}"
                )

    secret_keys: set[str] = set()
    extra_query: dict[str, str] = {}
    pagination = op.response.pagination
    if pagination and pagination.type == "offset":
        extra_query[pagination.limit_param or "limit"] = str(pagination.page_size)
        extra_query[pagination.offset_param or "offset"] = "0"

    req = _build_rendered_request(
        op.request,
        fields=fields,
        cred_fields=cred_fields,
        secret_keys=secret_keys,
        extra_query=extra_query or None,
    )

    if cred_row is not None:
        ct = resolve_cred_type(cred_type_name)
        oauth_token: str | None = None
        if ct.auth.strategy == "oauth2":
            if session is None:
                raise IntegrationError("oauth2 requires a database session")
            oauth_token = await _resolve_oauth_access_token(
                cred_row, cred_fields, session, transport=transport
            )
        await inject_auth(
            req,
            cred_type=ct,
            cred_fields=cred_fields,
            oauth_token=oauth_token,
        )

    hooks = get_hooks(app)
    if hooks and hooks.before_request:
        maybe = hooks.before_request(app, resource, operation, req, fields)
        if maybe is not None:
            await maybe

    max_pages = pagination.max_pages if pagination else 1
    max_items = settings.max_items_per_node
    all_records: list[dict[str, Any]] = []
    truncated = False
    cursor: str | None = None
    page_index = 0
    last_http: dict[str, Any] = {}

    for page in range(max_pages):
        page_req = req
        if page > 0 and pagination:
            nq = _next_page_query(
                pagination, last_http, page_index=page_index, cursor=cursor
            )
            if not nq:
                break
            if "__next_url__" in nq:
                page_req = RenderedRequest(
                    method=req.method,
                    url=nq["__next_url__"],
                    query={},
                    headers=dict(req.headers),
                    body=req.body,
                    body_kind=req.body_kind,
                    secret_keys=req.secret_keys,
                )
            else:
                extra_body: dict[str, str] | None = None
                extra_q = dict(nq)
                if pagination.type == "cursor" and pagination.cursor_location == "body":
                    param = pagination.cursor_param or "cursor"
                    if param in extra_q:
                        extra_body = {param: extra_q.pop(param)}
                page_req = _build_rendered_request(
                    op.request,
                    fields=fields,
                    cred_fields=cred_fields,
                    secret_keys=secret_keys,
                    extra_query=extra_q or None,
                )
                if extra_body:
                    page_req.body = _merge_body_cursor(
                        page_req.body,
                        param=next(iter(extra_body)),
                        cursor=next(iter(extra_body.values())),
                    )
                if cred_row is not None:
                    ct = resolve_cred_type(cred_type_name)
                    oauth_token = None
                    if ct.auth.strategy == "oauth2" and session is not None:
                        oauth_token = await _resolve_oauth_access_token(
                            cred_row, cred_fields, session, transport=transport
                        )
                    await inject_auth(
                        page_req,
                        cred_type=ct,
                        cred_fields=cred_fields,
                        oauth_token=oauth_token,
                    )
                if hooks and hooks.before_request:
                    maybe = hooks.before_request(
                        app, resource, operation, page_req, fields
                    )
                    if maybe is not None:
                        await maybe

        last_http = await _execute_page(
            page_req, transport=transport, timeout_ms=15_000
        )
        if hooks and hooks.check_response:
            hooks.check_response(app, resource, operation, last_http)
        page_records = _items_from_response(last_http, op)
        if hooks and hooks.map_items:
            mapped = hooks.map_items(
                app, resource, operation, last_http, op, fields, page_records
            )
            if mapped is not None:
                page_records = mapped
        remaining = max_items - len(all_records)
        if remaining <= 0:
            truncated = True
            break
        if len(page_records) > remaining:
            all_records.extend(page_records[:remaining])
            truncated = True
            break
        all_records.extend(page_records)

        page_index += 1
        if not pagination or page + 1 >= max_pages:
            break
        payload = last_http.get("json") or {}
        if pagination.type == "cursor":
            if not pagination.cursor_path:
                break
            try:
                cursor_val = resolve_path(payload, pagination.cursor_path)
            except ValueError:
                break
            if not cursor_val:
                break
            cursor = str(cursor_val)
        elif pagination.type == "offset":
            if len(page_records) < pagination.page_size:
                break
        elif pagination.type == "link_header":
            if not _parse_link_header(
                last_http.get("headers") or {}, pagination.link_header_rel
            ):
                break

    summary = {
        "method": req.method,
        "url": req.url,
        "query": req.query,
        "headers": req.headers,
    }
    redacted = redact_request_summary(summary, req.secret_keys)
    output: dict[str, Any] = {
        "request": redacted,
        "status": last_http.get("status"),
        "truncated": truncated,
        "pages_fetched": page_index,
    }
    items = [Item(json=r) for r in all_records]
    result = NodeResult.from_items(items)
    result.output = {**result.output, **output}
    return result