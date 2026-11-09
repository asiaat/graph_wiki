"""Document chunking for long-form source material.

The virtual experts are given a bounded window of the document. Reports in an
open-source corpus routinely exceed that window - 10 of the 52 documents in
the Berlin-2026 corpus are over 10,000 characters, the largest at 37,088 -
and everything past the cut was silently dropped.

The rule that matters: **the model sees a chunk, the verifier sees the whole
document**. A quote that straddles a chunk boundary must still be located in
the source, so the entailment gate always runs against the full text and the
character offsets it derives are global.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Target size of a chunk. The expert prompt is prefixed with the output
#: contract, so the usable budget is a little under this.
DEFAULT_MAX_CHARS = 8000

#: Overlap between consecutive hard-split chunks, so a sentence cut in half
#: by the split is still whole in one of them.
DEFAULT_OVERLAP = 300

_HEADING_RE = re.compile(r"^#{1,3} .+$", re.MULTILINE)


@dataclass(frozen=True)
class DocumentChunk:
    """One window of the source document."""

    index: int
    text: str
    start_char: int
    end_char: int

    @property
    def length(self) -> int:
        return self.end_char - self.start_char


def _split_on_headings(text: str, start: int) -> list[tuple[int, int]]:
    """Return (start, end) spans of the document split at markdown headings."""
    marks = [0]
    for match in _HEADING_RE.finditer(text):
        if match.start() > 0:
            marks.append(match.start())
    marks.append(len(text))

    spans: list[tuple[int, int]] = []
    for i in range(len(marks) - 1):
        begin, end = marks[i], marks[i + 1]
        if text[begin:end].strip():
            spans.append((begin, end))
    return spans


def _split_paragraphs(text: str, start: int, max_chars: int) -> list[tuple[int, int]]:
    """Split a section on blank lines."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for block in text.split("\n\n"):
        begin = start + pos
        end = begin + len(block)
        pos += len(block) + 2
        if not block.strip():
            continue
        if end - begin > max_chars:
            spans.extend(_hard_split(text, begin, end, max_chars))
        else:
            spans.append((begin, end))
    return spans


def _hard_split(
    text: str, start: int, end: int, max_chars: int, overlap: int = DEFAULT_OVERLAP
) -> list[tuple[int, int]]:
    """Cut an over-long block into overlapping windows."""
    spans: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + max_chars, end)
        if stop < end:
            # Prefer a sentence boundary near the cut.
            window = text[cursor:stop]
            for boundary in (". ", ".\n", "\n\n", " "):
                pos = window.rfind(boundary)
                if pos > max_chars * 0.5:
                    stop = cursor + pos + len(boundary)
                    break
        spans.append((cursor, stop))
        if stop >= end:
            break
        cursor = max(cursor + 1, stop - overlap)
    return spans


def chunk_document(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[DocumentChunk]:
    """Split ``text`` into chunks that each fit the expert's context window.

    Splits on markdown headings first (so a chunk is a coherent section),
    then on blank lines, and only then hard-splits with an overlap.
    """
    if not text:
        return []
    if len(text) <= max_chars:
        return [DocumentChunk(index=0, text=text, start_char=0, end_char=len(text))]

    spans: list[tuple[int, int]] = []
    for section_start, section_end in _split_on_headings(text, 0):
        section = text[section_start:section_end]
        if len(section) <= max_chars:
            spans.append((section_start, section_end))
        else:
            spans.extend(_split_paragraphs(section, section_start, max_chars))

    # Pack consecutive sections into one chunk. Splitting per heading would
    # turn a report with 40 headings into 40 chunks - and 40 chunks means
    # 120 model calls for a single document. A 37,088-character report becomes
    # five chunks this way.
    packed: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end = 0
    for start, end in spans:
        if current_start is None:
            current_start, current_end = start, end
        elif end - current_start <= max_chars:
            current_end = end
        else:
            packed.append((current_start, current_end))
            current_start, current_end = start, end
    if current_start is not None:
        packed.append((current_start, current_end))

    chunks: list[DocumentChunk] = []
    for begin, end in packed:
        chunk_text = text[begin:end].strip()
        if not chunk_text:
            continue
        # Recompute the offsets against the stripped text so they point at the
        # exact characters the model was shown.
        offset = text.find(chunk_text, begin, end + 1)
        if offset < 0:
            offset = begin
        chunks.append(
            DocumentChunk(
                index=len(chunks),
                text=chunk_text,
                start_char=offset,
                end_char=offset + len(chunk_text),
            )
        )

    logger.debug(
        "Chunked %d characters into %d chunk(s) (max %d)",
        len(text),
        len(chunks),
        max_chars,
    )
    return chunks
