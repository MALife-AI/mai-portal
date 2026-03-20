"""PDF-specific conversion logic using Marker for layout-aware conversion.

Converts PDF files to Pandoc AST JSON via:
  PDF → Marker (layout analysis) → Markdown → Pandoc AST JSON

Also supports embedded image extraction from PDF files.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default limits to protect against resource exhaustion
DEFAULT_PAGE_LIMIT = 500
DEFAULT_MARKER_TIMEOUT = 300  # seconds
DEFAULT_PANDOC_TIMEOUT = 60   # seconds
DEFAULT_PDFIMAGES_TIMEOUT = 60  # seconds


class PDFConversionError(Exception):
    """Raised when PDF conversion fails."""


class PDFPageLimitError(PDFConversionError):
    """Raised when a PDF exceeds the configured page limit."""


class PDFTimeoutError(PDFConversionError):
    """Raised when PDF conversion exceeds the configured timeout."""


@dataclass
class MarkerOptions:
    """Configuration options forwarded to the ``marker_single`` CLI.

    Attributes:
        batch_multiplier: Controls GPU batch size (marker ``--batch_multiplier``).
        max_pages: Hard cap on pages processed; None means unlimited.
        langs: Comma-separated language hints passed to ``--langs``.
        disable_image_extraction: Skip image extraction during conversion.
        extra_args: Any additional raw CLI arguments appended verbatim.
    """

    batch_multiplier: int = 2
    max_pages: int | None = None
    langs: str | None = None
    disable_image_extraction: bool = False
    extra_args: list[str] = field(default_factory=list)

    def to_cli_args(self) -> list[str]:
        """Return the CLI argument list to append to ``marker_single``."""
        args: list[str] = []
        args += ["--batch_multiplier", str(self.batch_multiplier)]
        if self.max_pages is not None:
            args += ["--max_pages", str(self.max_pages)]
        if self.langs:
            args += ["--langs", self.langs]
        if self.disable_image_extraction:
            args.append("--disable_image_extraction")
        args.extend(self.extra_args)
        return args


class PDFConverter:
    """Converts PDF files to Pandoc AST JSON using Marker for layout analysis.

    The conversion pipeline is:
        PDF → marker_single → Markdown → pandoc -t json → dict

    Image extraction uses ``pdfimages`` (poppler-utils) when available and
    falls back to scanning the Marker output directory for any PNG/JPEG files
    that Marker extracted during conversion.

    Args:
        marker_options: Fine-grained options forwarded to the Marker CLI.
        page_limit: Maximum number of pages allowed. Files exceeding this
            raise :exc:`PDFPageLimitError`. ``None`` disables the check.
        marker_timeout: Seconds before the Marker subprocess is killed.
        pandoc_timeout: Seconds before the Pandoc subprocess is killed.
    """

    def __init__(
        self,
        marker_options: MarkerOptions | None = None,
        page_limit: int | None = DEFAULT_PAGE_LIMIT,
        marker_timeout: int = DEFAULT_MARKER_TIMEOUT,
        pandoc_timeout: int = DEFAULT_PANDOC_TIMEOUT,
    ) -> None:
        self.marker_options = marker_options or MarkerOptions()
        self.page_limit = page_limit
        self.marker_timeout = marker_timeout
        self.pandoc_timeout = pandoc_timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def convert(self, file_path: Path) -> dict[str, Any]:
        """Convert a PDF file to a Pandoc AST JSON dict.

        Args:
            file_path: Absolute path to the source PDF.

        Returns:
            A Pandoc AST JSON object (top-level ``{"pandoc-api-version": ...,
            "meta": ..., "blocks": [...]}`` dict).

        Raises:
            PDFPageLimitError: When the document exceeds :attr:`page_limit`.
            PDFTimeoutError: When Marker or Pandoc times out.
            PDFConversionError: For all other conversion failures.
        """
        if not file_path.exists():
            raise PDFConversionError(f"File not found: {file_path}")

        self._check_page_limit(file_path)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_text = self._run_marker(file_path, tmp_path)
            return self._markdown_to_ast(md_text)

    def extract_images(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Extract embedded images from a PDF into *output_dir*.

        Attempts extraction with ``pdfimages`` (poppler-utils). If the tool is
        not installed, re-runs Marker in a temp directory and copies any
        image files it produced.

        Args:
            file_path: Absolute path to the source PDF.
            output_dir: Directory where extracted images are written.

        Returns:
            Sorted list of :class:`~pathlib.Path` objects for every image
            that was successfully written to *output_dir*.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        extracted = self._extract_via_pdfimages(file_path, output_dir)
        if extracted:
            return extracted

        logger.debug(
            "pdfimages not available or produced no output for %s; "
            "falling back to Marker image extraction",
            file_path.name,
        )
        return self._extract_via_marker(file_path, output_dir)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_page_limit(self, file_path: Path) -> None:
        """Raise :exc:`PDFPageLimitError` if the PDF exceeds *page_limit*."""
        if self.page_limit is None:
            return

        try:
            result = subprocess.run(
                ["pdfinfo", str(file_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.splitlines():
                if line.lower().startswith("pages:"):
                    pages = int(line.split(":", 1)[1].strip())
                    if pages > self.page_limit:
                        raise PDFPageLimitError(
                            f"PDF has {pages} pages which exceeds the limit of "
                            f"{self.page_limit}. Set page_limit=None to disable "
                            "this check or use MarkerOptions.max_pages to truncate."
                        )
                    return
        except PDFPageLimitError:
            raise
        except Exception as exc:  # pdfinfo not installed or parse error
            logger.debug("Could not determine page count for %s: %s", file_path.name, exc)

    def _run_marker(self, file_path: Path, tmp_path: Path) -> str:
        """Run ``marker_single`` and return the resulting Markdown text.

        Args:
            file_path: Source PDF path.
            tmp_path: Temporary directory used as Marker output root.

        Returns:
            Markdown string produced by Marker.

        Raises:
            PDFTimeoutError: On subprocess timeout.
            PDFConversionError: If Marker produces no Markdown output.
        """
        cmd = (
            ["marker_single", str(file_path), str(tmp_path)]
            + self.marker_options.to_cli_args()
        )
        logger.debug("Running Marker: %s", " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.marker_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise PDFTimeoutError(
                f"Marker timed out after {self.marker_timeout}s for {file_path.name}"
            ) from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode(errors="replace")[:500]
            logger.warning("Marker exited with %d: %s", proc.returncode, stderr)
            # Non-zero exit does not always mean failure — check for output first.

        md_files = sorted(tmp_path.glob("**/*.md"))
        if not md_files:
            stderr = (proc.stderr or b"").decode(errors="replace")[:500]
            raise PDFConversionError(
                f"Marker produced no Markdown output for {file_path.name}. "
                f"stderr: {stderr}"
            )

        # If Marker splits across multiple .md files, concatenate in order
        # and inject page markers for downstream page tracking.
        parts: list[str] = []
        for page_num, md_file in enumerate(md_files, 1):
            try:
                text = md_file.read_text(encoding="utf-8")
                parts.append(f"<!-- page:{page_num} -->\n{text}")
            except OSError as exc:
                logger.warning("Could not read Marker output %s: %s", md_file, exc)

        return "\n\n".join(parts)

    def _markdown_to_ast(self, md_text: str) -> dict[str, Any]:
        """Convert a Markdown string to a Pandoc AST JSON dict.

        Args:
            md_text: Markdown source text.

        Returns:
            Parsed Pandoc AST dict.

        Raises:
            PDFTimeoutError: On subprocess timeout.
            PDFConversionError: If Pandoc fails or returns invalid JSON.
        """
        try:
            result = subprocess.run(
                ["pandoc", "-f", "markdown", "-t", "json"],
                input=md_text,
                capture_output=True,
                text=True,
                timeout=self.pandoc_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise PDFTimeoutError(
                f"Pandoc timed out after {self.pandoc_timeout}s during AST conversion"
            ) from exc

        if result.returncode != 0:
            raise PDFConversionError(
                f"Pandoc failed (exit {result.returncode}): {result.stderr[:500]}"
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PDFConversionError(
                f"Pandoc returned invalid JSON: {exc}"
            ) from exc

    def _extract_via_pdfimages(
        self, file_path: Path, output_dir: Path
    ) -> list[Path]:
        """Use ``pdfimages -all`` to extract images.

        Returns an empty list when pdfimages is not installed or produces no
        output, so the caller can fall back to another strategy.
        """
        prefix = output_dir / file_path.stem
        try:
            proc = subprocess.run(
                ["pdfimages", "-all", str(file_path), str(prefix)],
                capture_output=True,
                timeout=DEFAULT_PDFIMAGES_TIMEOUT,
            )
        except FileNotFoundError:
            logger.debug("pdfimages not found; skipping poppler extraction")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("pdfimages timed out for %s", file_path.name)
            return []

        if proc.returncode != 0:
            logger.debug(
                "pdfimages failed (exit %d) for %s",
                proc.returncode,
                file_path.name,
            )
            return []

        image_extensions = {".png", ".jpg", ".jpeg", ".ppm", ".pbm", ".tif", ".tiff"}
        images = sorted(
            p for p in output_dir.iterdir() if p.suffix.lower() in image_extensions
        )
        return images

    def _extract_via_marker(
        self, file_path: Path, output_dir: Path
    ) -> list[Path]:
        """Re-run Marker to collect images it extracts during layout analysis."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cmd = ["marker_single", str(file_path), str(tmp_path)] + self.marker_options.to_cli_args()
            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=self.marker_timeout,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning("Marker image extraction failed for %s: %s", file_path.name, exc)
                return []

            image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
            collected: list[Path] = []
            for img_src in sorted(tmp_path.glob("**/*")):
                if img_src.suffix.lower() in image_extensions and img_src.is_file():
                    dest = output_dir / img_src.name
                    try:
                        import shutil
                        shutil.copy2(img_src, dest)
                        collected.append(dest)
                    except OSError as exc:
                        logger.warning("Could not copy image %s: %s", img_src, exc)

        return collected
