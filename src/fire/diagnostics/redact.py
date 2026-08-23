"""Secret redaction for logs, crash reports and support bundles.

Assume anything written to disk may be emailed to us by a customer and may end
up in a ticketing system. So redaction runs at the WRITE boundary, not when a
bundle is generated: a secret that reaches a log file has already leaked.

The patterns below are deliberately greedy. A false positive costs us a
slightly less readable log. A false negative costs a customer their account.
"""
from __future__ import annotations

import re
from typing import Any

MASK = "[redacted]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM blocks, whole thing, any label
    (re.compile(r"-----BEGIN[^-]{0,40}-----.*?-----END[^-]{0,40}-----", re.S), MASK),
    # bare private key bodies that lost their header
    (re.compile(r"\bMII[A-Za-z0-9+/=]{40,}"), MASK),
    # key=value secrets in config dumps and query strings
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret|password|passphrase|"
                r"private[_-]?key|token|authorization|bearer|licence[_-]?key|"
                r"license[_-]?key)\b(\s*[:=]\s*|\"\s*:\s*\"?)([^\s,;\"'}]{4,})"),
     r"\1\2" + MASK),
    # HTTP auth headers
    (re.compile(r"(?i)(KALSHI-ACCESS-(?:KEY|SIGNATURE|TIMESTAMP)\s*[:=]\s*)(\S+)"),
     r"\1" + MASK),
    # UUID-shaped identifiers (key IDs)
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), MASK),
    # base64 signatures
    (re.compile(r"\b[A-Za-z0-9+/]{86,}={0,2}\b"), MASK),
    # email addresses
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), MASK),
    # windows user paths reveal the customer's name
    (re.compile(r"(?i)([A-Z]:\\Users\\)([^\\\s\"']+)"), r"\1" + MASK),
    (re.compile(r"(/(?:home|Users)/)([^/\s\"']+)"), r"\1" + MASK),
)

_SECRET_KEYS = re.compile(
    r"(?i)(key|secret|token|password|passphrase|signature|credential|licence|license)"
)


def redact_text(text: str) -> str:
    if not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact_obj(obj: Any) -> Any:
    """Walk a JSON-ish structure, masking by key name and by value pattern."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEYS.search(k):
                out[k] = MASK
            else:
                out[k] = redact_obj(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def assert_clean(text: str) -> None:
    """Last line of defence before a bundle is written. Raises if anything
    that looks like a credential survived."""
    danger = (
        re.compile(r"-----BEGIN"),
        re.compile(r"\bMII[A-Za-z0-9+/=]{40,}"),
        re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    )
    for pattern in danger:
        if pattern.search(text):
            raise AssertionError(
                f"Support bundle blocked: unredacted secret matched {pattern.pattern!r}"
            )
