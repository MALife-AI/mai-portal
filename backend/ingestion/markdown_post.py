"""Markdown Post-Processor: GFM 검역소."""
from __future__ import annotations

import re
from html.parser import HTMLParser


def post_process(md: str) -> str:
    """변환된 마크다운을 GFM 규격으로 정규화."""
    md = _force_h1(md)
    md = _convert_html_tables(md)
    md = _strip_html_tags(md)
    md = _normalize_tables(md)
    md = _collapse_blank_lines(md)
    return md.strip() + "\n"


def _force_h1(md: str) -> str:
    """첫 번째 제목을 H1(#)으로 강제."""
    lines = md.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            lines[i] = f"# {m.group(2)}"
            break
    return "\n".join(lines)


# ── HTML Table → GFM Markdown Table ──────────────────────────────────────────

class _TableParser(HTMLParser):
    """HTML <table> 블록을 파싱하여 GFM 마크다운 표로 변환."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False
        self._in_thead = False
        self._header_row_count = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "thead":
            self._in_thead = True
        elif tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []
        elif tag == "tr":
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._in_thead = False
        elif tag in ("td", "th"):
            self._in_cell = False
            text = " ".join("".join(self._current_cell).split()).strip()
            self._current_row.append(text)
        elif tag == "tr":
            if self._current_row:
                self._rows.append(self._current_row)
                if self._in_thead:
                    self._header_row_count += 1

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)

    def to_gfm(self) -> str:
        if not self._rows:
            return ""
        # 열 수 통일
        max_cols = max(len(r) for r in self._rows)
        for r in self._rows:
            while len(r) < max_cols:
                r.append("")

        lines: list[str] = []
        header_idx = max(self._header_row_count, 1)  # 최소 1행을 헤더로

        for i, row in enumerate(self._rows):
            lines.append("| " + " | ".join(row) + " |")
            if i == header_idx - 1:
                lines.append("| " + " | ".join("---" for _ in row) + " |")

        return "\n".join(lines)


def _convert_html_tables(md: str) -> str:
    """본문 내 <table>...</table> 블록을 GFM 마크다운 표로 변환."""
    # HTML table 블록 추출 (multiline, non-greedy)
    table_pattern = re.compile(
        r"<table[^>]*>.*?</table>",
        re.DOTALL | re.IGNORECASE,
    )

    def _replace(match: re.Match) -> str:
        parser = _TableParser()
        try:
            parser.feed(match.group(0))
            gfm = parser.to_gfm()
            return f"\n{gfm}\n" if gfm else ""
        except Exception:
            return ""  # 파싱 실패 시 제거

    return table_pattern.sub(_replace, md)


def _strip_html_tags(md: str) -> str:
    """불필요한 HTML 태그 제거. img만 보존."""
    # 이미 변환된 table은 없으므로 잔여 태그 모두 제거
    md = re.sub(
        r"</?(?:div|span|font|center|br|table|thead|tbody|tfoot|tr|td|th|"
        r"colgroup|col|caption|style|p|ul|ol|li|a|b|i|u|em|strong|"
        r"h[1-6]|section|article|header|footer|nav|main|aside|figure|"
        r"figcaption|blockquote|pre|code|sub|sup|s|del|ins|mark|small|"
        r"abbr|details|summary|dl|dt|dd|hr)\s*/?>",
        "",
        md,
        flags=re.IGNORECASE,
    )
    # 속성이 있는 닫는 태그는 위에서 못 잡을 수 있으므로 추가 처리
    md = re.sub(r"</?[a-z][a-z0-9]*(?:\s+[^>]*)?>", "", md, flags=re.IGNORECASE)
    # img 태그 복원은 불필요 (위 패턴에 img 미포함이지만 만약을 위해)
    return md


def _normalize_tables(md: str) -> str:
    """GFM 테이블 정규화: 파이프 정렬."""
    lines = md.split("\n")
    result = []
    for line in lines:
        if "|" in line and re.match(r"^\|.*\|$", line.strip()):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            result.append("| " + " | ".join(cells) + " |")
        else:
            result.append(line)
    return "\n".join(result)


def _collapse_blank_lines(md: str) -> str:
    """연속된 빈 줄을 2줄로 제한."""
    return re.sub(r"\n{3,}", "\n\n", md)


# ── pdftotext -layout 텍스트 → GFM 테이블 변환 ─────────────────────────────

def convert_layout_tables(text: str) -> str:
    """pdftotext -layout 출력에서 공백 정렬된 표를 GFM 마크다운 테이블로 변환.

    공백 2개 이상으로 구분된 열이 3행 이상 연속되면 테이블로 인식한다.
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        # 테이블 후보 행 수집: 공백 2+ 로 구분된 2+ 열이 연속 3행 이상
        table_lines: list[str] = []
        j = i
        while j < len(lines):
            cols = _split_layout_columns(lines[j])
            if len(cols) >= 2:
                table_lines.append(lines[j])
                j += 1
            else:
                break

        if len(table_lines) >= 3:
            gfm = _layout_lines_to_gfm(table_lines)
            if gfm:
                result.append(gfm)
                i = j
                continue

        result.append(lines[i])
        i += 1

    return "\n".join(result)


def _split_layout_columns(line: str) -> list[str]:
    """공백 2개 이상을 구분자로 열을 분리."""
    stripped = line.strip()
    if not stripped:
        return []
    parts = re.split(r" {2,}", stripped)
    return [p.strip() for p in parts if p.strip()]


def _layout_lines_to_gfm(lines: list[str]) -> str:
    """공백 정렬된 행 목록을 GFM 테이블 문자열로 변환."""
    rows = [_split_layout_columns(line) for line in lines]
    if not rows:
        return ""

    max_cols = max(len(r) for r in rows)
    # 열 수가 너무 불균일하면 테이블이 아님
    col_counts = [len(r) for r in rows]
    mode_count = max(set(col_counts), key=col_counts.count)
    matching = sum(1 for c in col_counts if c == mode_count)
    if matching < len(rows) * 0.6:
        return ""

    for r in rows:
        while len(r) < max_cols:
            r.append("")

    gfm_lines: list[str] = []
    for idx, row in enumerate(rows):
        gfm_lines.append("| " + " | ".join(row) + " |")
        if idx == 0:
            gfm_lines.append("| " + " | ".join("---" for _ in row) + " |")

    return "\n".join(gfm_lines)
