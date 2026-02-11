from __future__ import annotations

import re
from typing import Iterable, List

_DELIM_RE = re.compile(r"\s*(?:,|;|\band\b|&|/|\||\+|\n|\r)\s*", re.IGNORECASE)


def _ensure_str_list(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    try:
        return [str(x) for x in raw]
    except Exception:
        return []


def _split_tokens(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    # Split on common delimiters, keeping names clean
    parts = [p.strip() for p in _DELIM_RE.split(raw) if p and p.strip()]
    return parts if parts else ([raw] if raw else [])


_INVALID_TOKENS = {"n/a", "na", "not available", "deceased", "dead", "nan", "none", "null"}


def _first_name(name: str) -> str:
    # Take first word as first name; strip stray punctuation
    token = (name or "").strip()
    if not token:
        return ""
    # Remove enclosing punctuation
    token = token.strip(",;:/|+ ")
    # First whitespace-delimited piece
    first = token.split()[0]
    if first.lower() in _INVALID_TOKENS:
        return ""
    # Normalize casing later in message generator; return raw here
    return first


def parse_student_names(raw: str | list[str] | None) -> list[str]:
    """Parse raw student string(s) into an ordered list of first names.

    - Accepts a single string with delimiters or a list of strings
    - Splits on commas/semicolons/"and"/&/slashes/pipes/plus/newlines
    - Trims and de-duplicates while preserving order
    """
    pieces = _ensure_str_list(raw)
    tokens: list[str] = []
    for piece in pieces:
        # For each piece, split further by delimiters
        tokens.extend(_split_tokens(piece))

    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        first = _first_name(t)
        if not first:
            continue
        key = first.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(first)
    return out


def format_student_names(first_names: list[str] | None, max_names: int = 4) -> str:
    """Format first names into natural language with Oxford-style 'and'.

    Examples:
    - ["Alice"] -> "Alice"
    - ["Alice","Bob"] -> "Alice and Bob"
    - ["Alice","Bob","Carol"] -> "Alice, Bob, and Carol"
    Caps at max_names entries if provided.
    """
    names = [n for n in (first_names or []) if (n or "").strip()]
    if not names:
        return ""
    names = names[: max(1, int(max_names))]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"

