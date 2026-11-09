"""Tolerant JSON loading for machine-generated corpora.

Corpora written by an LLM contain files that are *almost* JSON: a trailing
comma, a stray token between a colon and its value, a mangled key. Three of
the 57 ``entities.json`` files in the Berlin-2026 corpus fail a strict parse
for exactly these reasons.

The loader repairs what it can and salvages what it cannot - and it always
reports what it did, because silently dropping half a file would be worse
than failing loudly.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
#: ``"key":some_token [`` - a stray identifier between the colon and the value.
_STRAY_VALUE_RE = re.compile(r"(:\s*)[A-Za-z_][A-Za-z0-9_]*\s*(\[[^\n]*\])")
#: A mangled key at the start of an object.
_MANGLED_KEY_RE = re.compile(r'^\s*":\s*"', re.MULTILINE)


class TolerantJSONResult:
    """The outcome of a tolerant load."""

    def __init__(self, data: Any, repaired: bool, salvaged: int, error: str | None = None):
        self.data = data
        self.repaired = repaired
        self.salvaged = salvaged
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None


def _strip_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _fix_stray_values(text: str) -> str:
    return _STRAY_VALUE_RE.sub(r"\1\2", text)


def _fix_mangled_keys(text: str) -> str:
    return _MANGLED_KEY_RE.sub('    "name": "', text)


def _salvage_array_items(text: str) -> list[Any]:
    """Extract and parse the individually well-formed items of an array.

    Used when the file as a whole is corrupt but most of its records are
    intact. Brace matching is done with a scanner that respects strings and
    escapes, so a brace inside a string does not throw off the depth count.
    """
    items: list[Any] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            if depth == 0:
                start = index
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0 and start >= 0:
                blob = text[start : index + 1]
                try:
                    items.append(json.loads(blob))
                except json.JSONDecodeError:
                    pass
                start = -1
    return items


def _salvage_by_records(text: str) -> list[Any]:
    """Salvage the well-formed records of a file whose middle is corrupt.

    Records in these files are separated by ``},`` at a fixed indent. Splitting
    on that boundary and parsing each record independently means a single
    mangled record costs one record, not the whole file.
    """
    records: list[Any] = []
    # Split on the record separator, keeping the delimiter.
    parts = re.split(r"(?=\n    \{\n)", text)
    for part in parts:
        blob = part.strip()
        if not blob or blob in {"{", "}", "{}", "[]"}:
            continue
        if not blob.startswith("{"):
            blob = "{" + blob
        if not blob.endswith("}"):
            blob = blob.rstrip(",") + "}"
        try:
            records.append(json.loads(blob))
        except json.JSONDecodeError:
            continue
    return records


_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]{1,160})"')


def _balanced_object(text: str, start: int) -> str | None:
    """Return the balanced ``{...}`` starting at ``start``, or ``None``."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _salvage_by_fields(text: str) -> list[dict[str, Any]]:
    """Recover records field by field from a file whose structure is broken.

    The record boundaries are gone, but the *fields* are still there. Each
    ``"name"`` starts a new record, and the window up to the next name holds
    that record's fields.
    """
    matches = list(_NAME_RE.finditer(text))
    if not matches:
        return []

    records: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        window = text[match.start() : end]
        record: dict[str, Any] = {"name": match.group(1)}

        sources = re.search(r'"sources"\s*:\s*\[([^\]]*)\]', window)
        if sources:
            record["sources"] = re.findall(r'"([^"]*)"', sources.group(1))
        aliases = re.search(r'"aliases"\s*:\s*\[([^\]]*)\]', window)
        if aliases:
            record["aliases"] = re.findall(r'"([^"]*)"', aliases.group(1))
        mentions = re.search(r'"mentions"\s*:\s*(\d+)', window)
        if mentions:
            record["mentions"] = int(mentions.group(1))
        first_seen = re.search(r'"first_seen"\s*:\s*"([^"]*)"', window)
        if first_seen:
            record["first_seen"] = first_seen.group(1)
        attributes = re.search(r'"attributes"\s*:\s*\{', window)
        if attributes:
            blob = _balanced_object(window, attributes.end() - 1)
            if blob:
                try:
                    record["attributes"] = json.loads(blob)
                except json.JSONDecodeError:
                    pass
        records.append(record)
    return records


def load_tolerant(path: str) -> TolerantJSONResult:
    """Load a JSON file, repairing and salvaging where necessary."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return TolerantJSONResult(None, False, 0, error=f"unreadable: {exc}")

    try:
        return TolerantJSONResult(json.loads(text), False, 0)
    except json.JSONDecodeError as exc:
        # Python unbinds the exception variable at the end of the block, so
        # keep the message in a name that survives.
        first_error = str(exc)
        logger.debug("%s: strict parse failed (%s)", path, first_error)

    # Attempt 1: targeted repairs.
    repaired_text = _fix_mangled_keys(_fix_stray_values(_strip_trailing_commas(text)))
    try:
        data = json.loads(repaired_text)
        logger.warning("%s: repaired and parsed", path)
        return TolerantJSONResult(data, True, 0)
    except json.JSONDecodeError:
        pass

    # Attempt 2: salvage the individually well-formed records.
    salvaged = _salvage_by_records(repaired_text)
    if not salvaged:
        salvaged = _salvage_array_items(repaired_text)
    if salvaged:
        logger.warning(
            "%s: salvaged %d record(s) from a corrupt file (%s)",
            path,
            len(salvaged),
            first_error,
        )
        return TolerantJSONResult(salvaged, True, len(salvaged))

    # Attempt 3: field-level recovery of a file whose structure is gone.
    by_fields = _salvage_by_fields(repaired_text)
    if by_fields:
        logger.warning(
            "%s: recovered %d record(s) field by field from a corrupt file (%s)",
            path,
            len(by_fields),
            first_error,
        )
        return TolerantJSONResult(by_fields, True, len(by_fields))

    return TolerantJSONResult(None, False, 0, error=first_error)
