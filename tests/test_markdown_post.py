"""Tests for backend.ingestion.markdown_post (post_process pipeline)."""
from __future__ import annotations

import textwrap

import pytest

from backend.ingestion.markdown_post import (
    _collapse_blank_lines,
    _force_h1,
    _normalize_tables,
    _strip_html_tags,
    post_process,
)


# ---------------------------------------------------------------------------
# test_force_h1
# ---------------------------------------------------------------------------


def test_force_h1_converts_h2_to_h1() -> None:
    """First heading that is H2 is promoted to H1."""
    md = "## My Heading\nContent.\n"
    result = _force_h1(md)

    assert result.startswith("# My Heading")


def test_force_h1_converts_h3_to_h1() -> None:
    """First heading that is H3 is promoted to H1."""
    md = "### Deep Heading\nBody.\n"
    result = _force_h1(md)

    assert result.startswith("# Deep Heading")


def test_force_h1_already_h1_unchanged() -> None:
    """An already-H1 heading is not double-promoted."""
    md = "# Correct Heading\nContent.\n"
    result = _force_h1(md)

    assert result.startswith("# Correct Heading")
    assert not result.startswith("## ")


def test_force_h1_only_first_heading_converted() -> None:
    """Only the FIRST heading is promoted; subsequent headings are untouched."""
    md = "## First\nContent.\n\n## Second\nMore.\n"
    result = _force_h1(md)

    lines = result.split("\n")
    assert lines[0] == "# First"
    # Second heading must remain H2
    assert any(line == "## Second" for line in lines)


def test_force_h1_no_heading_unchanged() -> None:
    """Content without any headings is returned as-is."""
    md = "Just plain text.\n"
    result = _force_h1(md)

    assert result == md


def test_force_h1_heading_text_preserved() -> None:
    """Heading text content is not altered, only the level marker."""
    md = "### Calculate Insurance Premium\nBody.\n"
    result = _force_h1(md)

    assert "Calculate Insurance Premium" in result


# ---------------------------------------------------------------------------
# test_strip_html
# ---------------------------------------------------------------------------


def test_strip_html_removes_div() -> None:
    """<div> and </div> tags are stripped."""
    md = "<div>Wrapped content</div>"
    result = _strip_html_tags(md)

    assert "<div>" not in result
    assert "</div>" not in result
    assert "Wrapped content" in result


def test_strip_html_removes_span() -> None:
    """<span> tags (with or without attributes) are stripped."""
    md = '<span class="highlight">Important</span>'
    result = _strip_html_tags(md)

    assert "<span" not in result
    assert "Important" in result


def test_strip_html_removes_font_tag() -> None:
    """<font> tags are stripped."""
    md = '<font color="red">Red text</font>'
    result = _strip_html_tags(md)

    assert "<font" not in result
    assert "Red text" in result


def test_strip_html_removes_center_tag() -> None:
    """<center> tags are stripped."""
    md = "<center>Centered</center>"
    result = _strip_html_tags(md)

    assert "<center>" not in result
    assert "Centered" in result


def test_strip_html_preserves_img_tag() -> None:
    """<img> tags must not be removed."""
    md = '# Title\n<img src="chart.png" alt="chart" />\nContent.\n'
    result = _strip_html_tags(md)

    assert "<img" in result


def test_strip_html_preserves_table_tag() -> None:
    """<table> tags must not be removed."""
    md = "<table><tr><td>cell</td></tr></table>"
    result = _strip_html_tags(md)

    assert "<table>" in result


def test_strip_html_removes_br_tag() -> None:
    """Self-closing <br/> is stripped."""
    md = "line one<br/>line two"
    result = _strip_html_tags(md)

    assert "<br" not in result


# ---------------------------------------------------------------------------
# test_normalize_tables
# ---------------------------------------------------------------------------


def test_normalize_tables_adds_spaces_around_cells() -> None:
    """Table rows are reformatted with spaces around cell content."""
    md = "|col1|col2|col3|\n|---|---|---|\n"
    result = _normalize_tables(md)

    # Each data row should follow "| content | content |" format
    lines = result.split("\n")
    assert lines[0] == "| col1 | col2 | col3 |"


def test_normalize_tables_strips_cell_whitespace() -> None:
    """Leading/trailing whitespace inside cells is stripped."""
    md = "|  A  |  B  |\n"
    result = _normalize_tables(md)

    assert "| A | B |" in result


def test_normalize_tables_non_table_lines_unchanged() -> None:
    """Regular paragraph lines are not modified."""
    md = "This is a normal paragraph.\n"
    result = _normalize_tables(md)

    assert result == md


def test_normalize_tables_separator_row_normalised() -> None:
    """Separator row (---|---) is also normalised."""
    md = "|---|---|\n"
    result = _normalize_tables(md)

    assert "| --- | --- |" in result


# ---------------------------------------------------------------------------
# test_collapse_blank_lines
# ---------------------------------------------------------------------------


def test_collapse_blank_lines_three_to_two() -> None:
    """Three consecutive newlines are collapsed to two."""
    md = "Para one.\n\n\nPara two.\n"
    result = _collapse_blank_lines(md)

    assert "\n\n\n" not in result
    assert "Para one." in result
    assert "Para two." in result


def test_collapse_blank_lines_many_to_two() -> None:
    """Five consecutive blank lines collapse to exactly two newlines."""
    md = "A\n\n\n\n\nB"
    result = _collapse_blank_lines(md)

    assert "\n\n\n" not in result


def test_collapse_blank_lines_two_unchanged() -> None:
    """Two consecutive newlines (standard paragraph break) are kept."""
    md = "Para one.\n\nPara two.\n"
    result = _collapse_blank_lines(md)

    assert "\n\nPara two." in result


def test_collapse_blank_lines_single_newline_unchanged() -> None:
    """A single newline within a paragraph is left alone."""
    md = "line one\nline two\n"
    result = _collapse_blank_lines(md)

    assert "line one\nline two" in result


# ---------------------------------------------------------------------------
# test_full_pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_produces_h1() -> None:
    """post_process promotes the first heading to H1."""
    md = "## Report Title\n\nContent.\n"
    result = post_process(md)

    assert result.startswith("# Report Title")


def test_full_pipeline_strips_div_tags() -> None:
    """post_process removes div tags."""
    md = "# Title\n<div>extra</div>\nContent.\n"
    result = post_process(md)

    assert "<div>" not in result
    assert "extra" in result


def test_full_pipeline_normalises_table() -> None:
    """post_process reformats inline table to spaced pipe format."""
    md = "# Title\n|A|B|\n|---|---|\n|1|2|\n"
    result = post_process(md)

    assert "| A | B |" in result


def test_full_pipeline_collapses_blank_lines() -> None:
    """post_process collapses excessive blank lines."""
    md = "# Title\n\n\n\nContent.\n"
    result = post_process(md)

    assert "\n\n\n" not in result


def test_full_pipeline_ends_with_single_newline() -> None:
    """post_process output ends with exactly one newline (strip + append)."""
    md = "## Title\nContent.\n\n\n"
    result = post_process(md)

    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_full_pipeline_end_to_end_realistic() -> None:
    """A realistic dirty document is cleaned correctly by the full pipeline."""
    dirty = textwrap.dedent("""\
        ### 보험료 산출 보고서

        <div class="wrapper">
        <span>요약:</span> 이번 분기 보험료 산출 결과입니다.
        </div>



        |상품코드|보험료|
        |---|---|
        |P001|50000|

        마무리 문장입니다.
    """)
    result = post_process(dirty)

    # Promoted to H1
    assert result.startswith("# 보험료 산출 보고서")
    # HTML stripped
    assert "<div" not in result
    assert "<span>" not in result
    # Blank lines collapsed (no triple newlines)
    assert "\n\n\n" not in result
    # Table normalised
    assert "| 상품코드 | 보험료 |" in result
    # Content preserved
    assert "이번 분기" in result
    assert "마무리 문장" in result
    # Ends with single newline
    assert result.endswith("\n")
