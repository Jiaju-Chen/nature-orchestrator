from __future__ import annotations

import re
from typing import Any


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _quote_in_text(quote: str, final_text: str) -> bool:
    if not quote:
        return True
    if quote in final_text:
        return True
    return _normalize_whitespace(quote) in _normalize_whitespace(final_text)


def _walk_final_text_quotes(value: Any, path: str = "$") -> list[tuple[str, str]]:
    quotes: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "final_text_quote" and isinstance(child, str):
                quotes.append((child_path, child))
            else:
                quotes.extend(_walk_final_text_quotes(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            quotes.extend(_walk_final_text_quotes(child, f"{path}[{index}]"))
    return quotes


def final_text_quote_issues(review: dict[str, Any], final_text: str, label: str = "final text") -> list[str]:
    """Return issues for reviewer quotes that are not recoverable from final text."""

    if not isinstance(review, dict):
        return ["review must be a mapping for final_text_quote validation"]
    issues: list[str] = []
    for path, quote in _walk_final_text_quotes(review):
        stripped = quote.strip()
        if not stripped:
            continue
        if "..." in stripped or "…" in stripped:
            issues.append(f"{path} uses an ellipsis instead of an exact {label} substring: {stripped}")
            continue
        if not _quote_in_text(stripped, final_text or ""):
            issues.append(f"{path} is not an exact substring of {label}: {stripped}")
    return issues
