"""Structured redaction helpers; raw payloads remain private, never support data."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

MASK = "***"
SENSITIVE_FIELDS = frozenset({"matkhau", "mat_khau", "password", "_password", "pwd",
    "_csrf", "csrf", "token", "api_key", "dse_sessionid", "dse_processorid", "dse_pageid",
    "tendn", "username", "_username", "mst", "masothue", "tax_code", "taxpayer_name",
    "captcha", "_verifycode", "authorization", "cookie"})
SAFE_QUERY_FIELDS = frozenset({"page", "size", "pageindex", "pagesize", "dse_operationname", "dse_nexteventname"})
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:" + "|".join(re.escape(key) for key in sorted(SENSITIVE_FIELDS))
    + r")[\"']?\s*[:=]\s*)(?:[\"'][^\"']*[\"']|[^\s,;&}\]]+)")


def sensitive(name: str) -> bool:
    key = name.casefold().replace("-", "_")
    return key in SENSITIVE_FIELDS or any(part in key for part in ("token", "csrf", "password", "sessionid"))


def safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.username is not None:
            host = MASK + "@" + host
        if parsed.port is not None:
            host += f":{parsed.port}"
        path = re.sub(r";[^/]*", ";***", parsed.path)
        path = re.sub(r"(?i)(?:\d{8,}|[a-f0-9]{32,})", MASK, path)
        return urlunsplit((parsed.scheme, host, path, "", ""))
    except ValueError:
        return "[URL redacted]"


def redact_data(value):
    if isinstance(value, dict):
        return {key: MASK if sensitive(str(key)) else redact_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(item, (list, tuple)) and len(item) == 2 for item in value):
            return [(key, MASK if sensitive(str(key)) else redact_data(item)) for key, item in value]
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            payload = json.loads(stripped)
            if isinstance(payload, (dict, list)):
                return json.dumps(redact_data(payload), ensure_ascii=False)
        except (ValueError, RecursionError):
            pass
    if "<" in text and re.search(r"<(?:html|input|form|textarea)\b", text, re.I):
        soup = BeautifulSoup(text, "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        for node in soup(["input", "textarea"]):
            if node.has_attr("value"):
                node["value"] = MASK
            if node.name == "textarea":
                node.string = MASK
        for node in soup.find_all(True):
            for name in list(node.attrs):
                if name in {"href", "action", "src"}:
                    node[name] = safe_url(str(node[name]))
                elif name.startswith("data-") or name.lower().startswith("on"):
                    node[name] = MASK
        text = str(soup)
    elif "=" in text and not re.search(r"\s", text) and not stripped.startswith(("http:", "https:")):
        pairs = parse_qsl(text, keep_blank_values=True)
        if pairs:
            return urlencode([(key, item if key.casefold() in SAFE_QUERY_FIELDS else MASK) for key, item in pairs], safe="*")
    text = _URL.sub(lambda match: safe_url(match.group()), text)
    text = _ASSIGNMENT.sub(lambda match: match.group(1) + MASK, text)
    text = re.sub(r"(?<!\w)\d{8,}(?!\w)", MASK, text)
    text = re.sub(r"(?i)([A-Z]:[\\/](?:Users|Documents and Settings)[\\/])[^\\/]+", r"\1***", text)
    return text


def exception_summary(exc_type, exc, tb) -> str:
    """Crash evidence contains frame locations, never source lines/locals/message."""
    import traceback
    from pathlib import Path
    frames = traceback.extract_tb(tb) if tb is not None else []
    locations = [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames]
    return f"{exc_type.__name__}: exception details omitted\n" + "\n".join(locations[-20:])
