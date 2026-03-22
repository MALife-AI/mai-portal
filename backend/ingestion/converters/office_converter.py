"""DOCX/PPTX conversion logic using Pandoc and standard library ZIP handling.

Conversion pipeline:
  DOCX/PPTX → pandoc -t json → Pandoc AST JSON dict

PPTX-specific extras:
  • convert_pptx_by_slide  — one AST dict per slide
  • extract_media          — pulls embedded media via zipfile

Speaker notes are extracted from PPTX slide XML and appended as a Pandoc
BlockQuote at the end of each slide's block list.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

PANDOC_TIMEOUT = 120    # seconds
# XML namespace used by OOXML presentation files
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PPTX_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_PPTX_NS_MAP = {
    "a": _DRAWINGML_NS,
    "p": _PPTX_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".docx", ".doc", ".pptx", ".xlsx", ".xls"})


class OfficeConversionError(Exception):
    """Raised when DOCX/PPTX conversion fails."""


class OfficeConverter:
    """Converts DOCX and PPTX files to Pandoc AST JSON dicts.

    For straightforward whole-document conversion the class delegates to
    ``pandoc``.  PPTX files can additionally be split into per-slide ASTs and
    have their embedded media extracted without running Pandoc.

    Args:
        pandoc_timeout: Seconds before any Pandoc subprocess is killed.
    """

    def __init__(self, pandoc_timeout: int = PANDOC_TIMEOUT) -> None:
        self.pandoc_timeout = pandoc_timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def convert(
        self, file_path: Path, *, media_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Convert a DOCX or PPTX file to a Pandoc AST JSON dict.

        Args:
            file_path: Absolute path to the source .docx, .doc, or .pptx.
            media_dir: If provided, embedded images are extracted here and
                AST image paths reference this directory so downstream VLM
                processing can access them.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            ValueError: If the extension is not supported.
            OfficeConversionError: If Pandoc times out or returns an error.
        """
        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"OfficeConverter does not support extension '{ext}'. "
                f"Supported: {SUPPORTED_EXTENSIONS}"
            )

        if not file_path.exists():
            raise OfficeConversionError(f"File not found: {file_path}")

        # XLSX는 Pandoc이 아닌 openpyxl로 처리
        if ext in (".xlsx", ".xls"):
            return self._xlsx_to_ast(file_path)

        return self._pandoc_to_ast(file_path, media_dir=media_dir)

    def _xlsx_to_ast(self, file_path: Path) -> dict[str, Any]:
        """XLSX를 Pandoc AST 호환 구조로 변환합니다."""
        try:
            import openpyxl
        except ImportError:
            raise OfficeConversionError("openpyxl이 설치되지 않았습니다: pip install openpyxl")

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        blocks: list[dict[str, Any]] = []

        for sheet in wb.worksheets:
            # 시트 제목
            blocks.append({
                "t": "Header",
                "c": [2, ["", [], []], [{"t": "Str", "c": sheet.title}]],
            })

            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue

            # GFM 테이블 형식의 AST 생성 (Plain text block으로)
            lines = []
            headers = [str(c) if c is not None else "" for c in rows[0]]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in rows[1:]:
                cells = [str(c).replace("|", "\\|").replace("\n", " ") if c is not None else "" for c in row]
                lines.append("| " + " | ".join(cells) + " |")

            table_md = "\n".join(lines)
            blocks.append({
                "t": "RawBlock",
                "c": ["markdown", table_md],
            })

        wb.close()

        return {
            "pandoc-api-version": [1, 23, 1],
            "meta": {},
            "blocks": blocks,
        }

    def convert_pptx_by_slide(self, file_path: Path) -> list[dict[str, Any]]:
        """Split a PPTX file into one Pandoc AST dict per slide.

        Each slide is converted individually by running ``pandoc`` on the
        whole file and then partitioning the top-level block list at
        ``HorizontalRule`` nodes (which Pandoc emits between slides).

        Speaker notes extracted directly from the PPTX XML are appended as a
        ``BlockQuote`` at the end of each slide's block list.

        Args:
            file_path: Absolute path to the source .pptx file.

        Returns:
            List of Pandoc AST dicts, one per slide, in presentation order.
            An empty list is returned if no slides are found.

        Raises:
            OfficeConversionError: If the file cannot be read as a PPTX ZIP.
        """
        if not file_path.exists():
            raise OfficeConversionError(f"File not found: {file_path}")

        full_ast = self._pandoc_to_ast(file_path)
        slide_blocks = self._split_blocks_by_slide(full_ast.get("blocks", []))
        speaker_notes = self._extract_speaker_notes(file_path)

        slides: list[dict[str, Any]] = []
        for idx, blocks in enumerate(slide_blocks):
            note = speaker_notes[idx] if idx < len(speaker_notes) else None
            if note:
                blocks = blocks + [self._note_to_block_quote(note)]

            slide_ast: dict[str, Any] = {
                "pandoc-api-version": full_ast.get("pandoc-api-version", []),
                "meta": {},
                "blocks": blocks,
            }
            slides.append(slide_ast)

        return slides

    def extract_media(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Extract all embedded media from a DOCX or PPTX file.

        Both formats are OOXML ZIP archives.  Media files live under
        ``word/media/`` (DOCX) or ``ppt/media/`` (PPTX).

        Args:
            file_path: Absolute path to the source .docx or .pptx.
            output_dir: Directory where extracted media files are written.
                Created if it does not exist.

        Returns:
            Sorted list of :class:`~pathlib.Path` objects for each extracted
            file, in ZIP entry order.

        Raises:
            OfficeConversionError: If the file is not a valid ZIP/OOXML archive.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        media_prefixes = ("word/media/", "ppt/media/", "xl/media/")

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                entries = [
                    e for e in zf.infolist()
                    if any(e.filename.startswith(p) for p in media_prefixes)
                    and not e.filename.endswith("/")
                ]
        except zipfile.BadZipFile as exc:
            raise OfficeConversionError(
                f"{file_path.name} is not a valid ZIP/OOXML archive: {exc}"
            ) from exc

        extracted: list[Path] = []
        with zipfile.ZipFile(file_path, "r") as zf:
            for entry in entries:
                name = Path(entry.filename).name
                dest = output_dir / name
                # Deduplicate: if the name already exists append an index.
                if dest.exists():
                    stem = Path(name).stem
                    suffix = Path(name).suffix
                    dest = output_dir / f"{stem}_{len(extracted)}{suffix}"
                try:
                    dest.write_bytes(zf.read(entry.filename))
                    extracted.append(dest)
                except Exception as exc:
                    logger.warning(
                        "Could not extract %s from %s: %s",
                        entry.filename,
                        file_path.name,
                        exc,
                    )

        return sorted(extracted)

    # ------------------------------------------------------------------
    # Pandoc helpers
    # ------------------------------------------------------------------

    def _pandoc_to_ast(
        self, file_path: Path, media_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Run ``pandoc <file> -t json --extract-media=<dir>``.

        Args:
            file_path: Office document to convert.
            media_dir: Directory to extract embedded media into. If provided,
                images are persisted here and AST image paths point to this
                directory. If ``None``, a temporary directory is used and
                discarded after conversion.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            OfficeConversionError: On timeout, non-zero exit, or bad JSON.
        """
        if media_dir is not None:
            media_dir.mkdir(parents=True, exist_ok=True)
            return self._run_pandoc_ast(file_path, media_dir)

        with tempfile.TemporaryDirectory() as tmp:
            return self._run_pandoc_ast(file_path, Path(tmp))

    def _run_pandoc_ast(self, file_path: Path, cwd: Path) -> dict[str, Any]:
        cmd = [
            "pandoc",
            str(file_path),
            "-t", "json",
            "--extract-media=.",
        ]
        logger.debug("Running Pandoc: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=self.pandoc_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficeConversionError(
                f"Pandoc timed out after {self.pandoc_timeout}s for {file_path.name}"
            ) from exc

        if result.returncode != 0:
            raise OfficeConversionError(
                f"Pandoc failed (exit {result.returncode}): {result.stderr[:500]}"
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise OfficeConversionError(
                f"Pandoc returned invalid JSON: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # PPTX slide-splitting helpers
    # ------------------------------------------------------------------

    def _split_blocks_by_slide(
        self, blocks: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        """Partition a flat block list into groups separated by HorizontalRule.

        Pandoc emits ``{"t": "HorizontalRule"}`` between slides when
        converting PPTX.  The HorizontalRule nodes are consumed (not included
        in any group).

        Args:
            blocks: Top-level ``blocks`` list from a Pandoc AST.

        Returns:
            List of block groups.  Always contains at least one group even if
            there are no HorizontalRule separators.
        """
        slides: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []

        for block in blocks:
            if isinstance(block, dict) and block.get("t") == "HorizontalRule":
                slides.append(current)
                current = []
            else:
                current.append(block)

        slides.append(current)
        # Drop any leading/trailing empty groups caused by leading/trailing rules.
        return [s for s in slides if s]

    def _extract_speaker_notes(self, file_path: Path) -> list[str]:
        """Parse PPTX XML to extract speaker notes for each slide.

        Speaker notes live in ``ppt/notesSlides/notesSlide<N>.xml``.  This
        method reads all such entries in natural sort order and extracts the
        plain text content.

        Args:
            file_path: Source .pptx file.

        Returns:
            List of plain-text note strings in slide order.  Slides with no
            notes are represented as empty strings.
        """
        notes: list[str] = []

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                # Collect notes slide entries in sorted order
                note_entries = sorted(
                    [e for e in zf.namelist() if e.startswith("ppt/notesSlides/notesSlide")],
                    key=lambda s: self._slide_index_from_path(s),
                )
                for entry in note_entries:
                    try:
                        xml_bytes = zf.read(entry)
                        text = self._parse_notes_xml(xml_bytes)
                        notes.append(text)
                    except Exception as exc:
                        logger.debug("Could not parse notes entry %s: %s", entry, exc)
                        notes.append("")
        except zipfile.BadZipFile as exc:
            logger.warning("Could not open %s as ZIP for notes extraction: %s", file_path.name, exc)

        return notes

    @staticmethod
    def _slide_index_from_path(path: str) -> int:
        """Return the numeric index from a ``notesSlide<N>.xml`` path."""
        stem = Path(path).stem  # e.g. "notesSlide3"
        digits = "".join(c for c in stem if c.isdigit())
        return int(digits) if digits else 0

    @staticmethod
    def _parse_notes_xml(xml_bytes: bytes) -> str:
        """Extract plain text from a PPTX notes slide XML fragment.

        Only text runs (``<a:t>``) inside the notes text box (``<p:notes>``)
        are returned.  The presentation slide thumbnail placeholder (sp idx=1)
        is skipped so only the actual note text is captured.

        Args:
            xml_bytes: Raw bytes of a ``notesSlide<N>.xml`` file.

        Returns:
            Concatenated plain text of all note paragraphs, separated by
            newlines.  Returns an empty string on parse failure.
        """
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return ""

        ns_a = _DRAWINGML_NS
        ns_p = _PPTX_NS

        lines: list[str] = []
        # Walk all spTree/sp elements; skip the slide image placeholder (idx=1)
        for sp in root.iter(f"{{{ns_p}}}sp"):
            # Check placeholder idx; skip idx=1 (slide thumbnail)
            ph = sp.find(
                f".//{{{ns_p}}}nvSpPr/{{{ns_p}}}nvPr/{{{ns_p}}}ph"
            )
            if ph is not None:
                idx = ph.get("idx", "0")
                try:
                    if int(idx) == 1:
                        continue
                except ValueError:
                    pass

            for para in sp.iter(f"{{{ns_a}}}p"):
                para_text = "".join(
                    t.text or ""
                    for t in para.iter(f"{{{ns_a}}}t")
                )
                if para_text.strip():
                    lines.append(para_text)

        return "\n".join(lines)

    @staticmethod
    def _note_to_block_quote(note_text: str) -> dict[str, Any]:
        """Wrap a notes string in a Pandoc BlockQuote AST node.

        The note text is split on newlines and each non-empty line becomes a
        separate ``Para`` block inside the ``BlockQuote``.

        Args:
            note_text: Plain text of the speaker note.

        Returns:
            A ``{"t": "BlockQuote", "c": [...Para blocks...]}`` AST node.
        """
        paras: list[dict[str, Any]] = []
        for line in note_text.splitlines():
            line = line.strip()
            if not line:
                continue
            paras.append({
                "t": "Para",
                "c": [{"t": "Str", "c": line}],
            })

        if not paras:
            paras = [{"t": "Para", "c": [{"t": "Str", "c": note_text}]}]

        return {"t": "BlockQuote", "c": paras}
