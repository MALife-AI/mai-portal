"""Semantic Chunking: 마크다운을 의미 단위로 분할.

Features:
- Heading-based structural splitting (H1-H3)
- Table-aware chunking: markdown tables are never split across chunks
- Frontmatter exclusion from chunk content (metadata handled upstream)
- Configurable overlap between adjacent chunks for context continuity
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A single chunk of a markdown document.

    Attributes:
        content: The chunk text, excluding frontmatter.
        heading: The nearest ancestor heading for this chunk.
        start_line: Line number (0-indexed) where this chunk begins in the
            stripped (no-frontmatter) document.
        metadata: Arbitrary key/value pairs attached by the caller.
    """

    content: str
    heading: str
    start_line: int
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_markdown(
    content: str,
    max_chunk_size: int = 1000,
    overlap: int = 100,
) -> list[Chunk]:
    """Split a markdown document into semantic chunks.

    Processing steps:
    1. Strip YAML frontmatter (``---`` blocks) so it never appears in chunk
       text.  Callers are responsible for parsing metadata separately.
    2. Split on H1-H3 headings, keeping tables intact within the section they
       belong to.
    3. Sub-split any section that still exceeds *max_chunk_size* at paragraph
       boundaries while preserving whole tables.
    4. Append an *overlap* suffix/prefix between consecutive chunks so
       embeddings share some neighbouring context.

    Args:
        content: Raw markdown string (may include frontmatter).
        max_chunk_size: Soft maximum character length per chunk before
            sub-splitting.  Tables that exceed this limit are kept whole.
        overlap: Number of characters taken from the end of chunk N and
            prepended to chunk N+1 (and vice-versa).  Set to 0 to disable.

    Returns:
        Ordered list of :class:`Chunk` objects.
    """
    body = _strip_frontmatter(content)
    sections = _split_by_headings(body)

    # Sub-split oversized sections, preserving tables
    flat: list[Chunk] = []
    for chunk in sections:
        if len(chunk.content) > max_chunk_size:
            parts = _split_large_table_aware(chunk.content, max_chunk_size)
            for part in parts:
                flat.append(Chunk(
                    content=part,
                    heading=chunk.heading,
                    start_line=chunk.start_line,
                    metadata=chunk.metadata,
                ))
        else:
            flat.append(chunk)

    # Remove empty chunks produced by any splitting step
    flat = [c for c in flat if c.content.strip()]

    if overlap > 0:
        flat = _apply_overlap(flat, overlap)

    return flat


# ---------------------------------------------------------------------------
# Frontmatter stripping
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n?",
    re.DOTALL,
)


def _strip_frontmatter(content: str) -> str:
    """Remove leading YAML frontmatter delimited by ``---`` fences.

    Args:
        content: Raw document text.

    Returns:
        Document body without the frontmatter block.
    """
    return _FRONTMATTER_RE.sub("", content, count=1)


# ---------------------------------------------------------------------------
# Heading-based splitting
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,3}\s+")
_PAGE_MARKER_RE = re.compile(r"<!--\s*page:(\d+)\s*-->")


def _split_by_headings(body: str) -> list[Chunk]:
    """Split *body* into sections at H1/H2/H3 boundaries.

    Tracks ``<!-- page:N -->`` markers to record page numbers in chunk
    metadata.
    """
    lines = body.split("\n")
    chunks: list[Chunk] = []
    current_heading = ""
    current_lines: list[str] = []
    start_line = 0
    current_page: int | None = None
    page_start: int | None = None

    for i, line in enumerate(lines):
        # Track page markers
        page_match = _PAGE_MARKER_RE.match(line.strip())
        if page_match:
            current_page = int(page_match.group(1))
            if page_start is None:
                page_start = current_page
            continue  # don't include marker in content

        if _HEADING_RE.match(line):
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    meta: dict = {}
                    if page_start is not None:
                        meta["page_start"] = page_start
                    if current_page is not None:
                        meta["page_end"] = current_page
                    chunks.append(Chunk(
                        content=text,
                        heading=current_heading,
                        start_line=start_line,
                        metadata=meta,
                    ))
            current_heading = line.lstrip("#").strip()
            current_lines = [line]
            start_line = i
            page_start = current_page
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            meta = {}
            if page_start is not None:
                meta["page_start"] = page_start
            if current_page is not None:
                meta["page_end"] = current_page
            chunks.append(Chunk(
                content=text,
                heading=current_heading,
                start_line=start_line,
                metadata=meta,
            ))

    return chunks


# ---------------------------------------------------------------------------
# Table-aware sub-splitting
# ---------------------------------------------------------------------------

def _split_large_table_aware(text: str, max_size: int) -> list[str]:
    """Split *text* at paragraph boundaries while keeping tables whole.

    A *block* is either a markdown table (consecutive lines starting with
    ``|``) or a regular paragraph (separated from neighbours by blank lines).
    Blocks are accumulated into parts until adding the next block would
    exceed *max_size*; at that point a new part is started.  A single block
    that is itself larger than *max_size* is emitted as its own part rather
    than being split further, so table integrity is always preserved.

    Args:
        text: Section text to sub-split.
        max_size: Soft maximum character budget per part.

    Returns:
        List of text parts, each within *max_size* characters (except
        indivisible table blocks).
    """
    blocks = _extract_blocks(text)
    parts: list[str] = []
    current_parts: list[str] = []

    def _joined_size() -> int:
        return len("\n\n".join(current_parts))

    for block in blocks:
        # 단일 블록이 한도를 초과하면 강제 분할
        if len(block) > max_size:
            if current_parts:
                parts.append("\n\n".join(current_parts).strip())
                current_parts = []
            for i in range(0, len(block), max_size):
                parts.append(block[i:i + max_size])
            continue

        if current_parts and _joined_size() + 2 + len(block) > max_size:
            parts.append("\n\n".join(current_parts).strip())
            current_parts = [block]
        else:
            current_parts.append(block)

    if current_parts:
        parts.append("\n\n".join(current_parts).strip())

    return [p for p in parts if p.strip()]


def _extract_blocks(text: str) -> list[str]:
    """Decompose *text* into table blocks and paragraph blocks.

    Consecutive lines beginning with ``|`` form a single table block.
    Everything else is split on blank lines into paragraph blocks.

    Args:
        text: Raw section text.

    Returns:
        Ordered list of block strings.
    """
    lines = text.split("\n")
    blocks: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("|"):
            # Consume the entire table
            table_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append("\n".join(table_lines))
        elif line.strip() == "":
            # Skip blank separator lines (they delimit paragraphs)
            i += 1
        else:
            # Consume a paragraph (ends at a blank line or a table line)
            para_lines: list[str] = []
            while i < len(lines) and lines[i].strip() != "" and not lines[i].startswith("|"):
                para_lines.append(lines[i])
                i += 1
            blocks.append("\n".join(para_lines))

    return [b for b in blocks if b.strip()]


# ---------------------------------------------------------------------------
# Overlap application
# ---------------------------------------------------------------------------

def _apply_overlap(chunks: list[Chunk], overlap: int) -> list[Chunk]:
    """Add trailing context from chunk N to the beginning of chunk N+1.

    The overlap text is taken character-by-character from the *end* of the
    previous chunk's content and prepended (with a ``\\n\\n`` separator) to
    the next chunk.  This keeps each chunk's ``start_line`` and ``heading``
    unchanged so callers can still reconstruct provenance.

    Args:
        chunks: Ordered list of chunks produced by the splitting stage.
        overlap: Maximum number of characters to copy between neighbours.

    Returns:
        New list of :class:`Chunk` objects with overlap applied.
    """
    if len(chunks) <= 1:
        return chunks

    result: list[Chunk] = []
    for idx, chunk in enumerate(chunks):
        new_content = chunk.content
        if idx > 0:
            prev_tail = chunks[idx - 1].content[-overlap:]
            new_content = prev_tail + "\n\n" + new_content
        result.append(Chunk(
            content=new_content,
            heading=chunk.heading,
            start_line=chunk.start_line,
            metadata=chunk.metadata,
        ))

    return result
