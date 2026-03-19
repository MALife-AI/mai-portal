"""Tests for backend.indexer.chunker (chunk_markdown)."""
from __future__ import annotations

import textwrap

import pytest

from backend.indexer.chunker import Chunk, chunk_markdown


# ---------------------------------------------------------------------------
# test_basic_chunking
# ---------------------------------------------------------------------------


def test_basic_chunking_splits_on_headings() -> None:
    """Content is split into one chunk per heading section."""
    md = textwrap.dedent("""\
        # Section One
        Content for section one.

        ## Section Two
        Content for section two.

        ### Section Three
        Content for section three.
    """)
    chunks = chunk_markdown(md)

    assert len(chunks) == 3
    headings = [c.heading for c in chunks]
    assert "Section One" in headings
    assert "Section Two" in headings
    assert "Section Three" in headings


def test_basic_chunking_returns_chunk_objects() -> None:
    """Each element returned is a Chunk dataclass instance."""
    md = "# Title\nSome text.\n"
    chunks = chunk_markdown(md)

    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)


def test_basic_chunking_heading_text_stripped() -> None:
    """Heading field contains the heading text without leading # characters."""
    md = "## My Heading\nBody text.\n"
    chunks = chunk_markdown(md)

    assert chunks[0].heading == "My Heading"


# ---------------------------------------------------------------------------
# test_large_chunk_split
# ---------------------------------------------------------------------------


def test_large_chunk_split_produces_multiple_chunks() -> None:
    """A single heading section longer than max_chunk_size is split further."""
    # Build two paragraphs each ~600 chars so combined > 1000 default limit
    para_a = "A" * 600
    para_b = "B" * 600
    md = f"# Big Section\n{para_a}\n\n{para_b}\n"

    chunks = chunk_markdown(md, max_chunk_size=1000)

    assert len(chunks) > 1


def test_large_chunk_split_each_part_within_limit() -> None:
    """After splitting, each chunk respects an explicit max_chunk_size."""
    para_a = "X" * 400
    para_b = "Y" * 400
    para_c = "Z" * 400
    md = f"# Oversized\n{para_a}\n\n{para_b}\n\n{para_c}\n"

    chunks = chunk_markdown(md, max_chunk_size=500)

    for chunk in chunks:
        assert len(chunk.content) <= 500, (
            f"Chunk exceeds max_chunk_size: {len(chunk.content)} chars"
        )


def test_large_chunk_split_same_heading_preserved() -> None:
    """All sub-chunks from an oversized section keep the original heading."""
    para_a = "P" * 600
    para_b = "Q" * 600
    md = f"# Original Heading\n{para_a}\n\n{para_b}\n"

    chunks = chunk_markdown(md, max_chunk_size=1000)

    for chunk in chunks:
        assert chunk.heading == "Original Heading"


# ---------------------------------------------------------------------------
# test_empty_content
# ---------------------------------------------------------------------------


def test_empty_content_returns_empty_list() -> None:
    """Empty string input produces no chunks."""
    chunks = chunk_markdown("")
    assert chunks == []


def test_whitespace_only_content_returns_empty_list() -> None:
    """Input with only whitespace produces no chunks."""
    chunks = chunk_markdown("   \n\n   ")
    assert chunks == []


# ---------------------------------------------------------------------------
# test_no_headings
# ---------------------------------------------------------------------------


def test_no_headings_produces_single_chunk() -> None:
    """Markdown with no heading lines is returned as one chunk."""
    md = textwrap.dedent("""\
        This is a paragraph.

        Another paragraph with more content.

        And a third one.
    """)
    chunks = chunk_markdown(md)

    assert len(chunks) == 1


def test_no_headings_chunk_has_empty_heading() -> None:
    """The single chunk produced from headingless content has an empty heading."""
    md = "Just plain content.\n"
    chunks = chunk_markdown(md)

    assert chunks[0].heading == ""


def test_no_headings_content_is_present() -> None:
    """Headingless chunk contains the original text."""
    md = "Plain content without any headings.\n"
    chunks = chunk_markdown(md)

    assert "Plain content without any headings." in chunks[0].content


# ---------------------------------------------------------------------------
# test_preserves_heading_in_chunk
# ---------------------------------------------------------------------------


def test_preserves_heading_line_in_chunk_content() -> None:
    """The heading line itself appears inside the chunk content."""
    md = "# My Section\nSome body.\n"
    chunks = chunk_markdown(md)

    assert "# My Section" in chunks[0].content


def test_preserves_heading_level_2_in_chunk_content() -> None:
    """H2 heading line is preserved inside the chunk content."""
    md = "## Sub Section\nBody.\n"
    chunks = chunk_markdown(md)

    assert "## Sub Section" in chunks[0].content


def test_start_line_recorded_correctly() -> None:
    """start_line reflects the 0-based line index where the chunk begins."""
    md = textwrap.dedent("""\
        # First
        line one

        # Second
        line two
    """)
    chunks = chunk_markdown(md)

    # First chunk starts at line 0
    assert chunks[0].start_line == 0
    # Second chunk starts at line 3 (0-indexed)
    assert chunks[1].start_line == 3


def test_metadata_dict_is_present() -> None:
    """Each Chunk carries a metadata dict (may be empty but must exist)."""
    md = "# Title\nbody\n"
    chunks = chunk_markdown(md)

    assert isinstance(chunks[0].metadata, dict)
