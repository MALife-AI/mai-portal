"""HWP/HWPX-specific conversion logic.

Conversion strategy (in priority order):
  1. LibreOffice headless  → DOCX → Pandoc AST JSON
  2. hwp5txt fallback      → plain text → Pandoc AST JSON

Image extraction reads the OLE compound document or ZIP (HWPX) container
directly to pull out embedded BinData / media files.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LIBREOFFICE_TIMEOUT = 120   # seconds
HWP5TXT_TIMEOUT = 60        # seconds
PANDOC_TIMEOUT = 60         # seconds


class HWPConversionError(Exception):
    """Raised when HWP/HWPX conversion fails via both strategies."""


class HWPConverter:
    """Converts HWP and HWPX documents to Pandoc AST JSON.

    Primary path: LibreOffice headless converts the file to DOCX, then Pandoc
    reads the DOCX and emits AST JSON.

    Fallback path: ``hwp5txt`` extracts plain text which is then fed to Pandoc
    as Markdown.  This loses most formatting but is robust.

    Args:
        libreoffice_timeout: Seconds before the LibreOffice subprocess is killed.
        hwp5txt_timeout: Seconds before the hwp5txt subprocess is killed.
        pandoc_timeout: Seconds before any Pandoc subprocess is killed.
    """

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".hwp", ".hwpx"})

    def __init__(
        self,
        libreoffice_timeout: int = LIBREOFFICE_TIMEOUT,
        hwp5txt_timeout: int = HWP5TXT_TIMEOUT,
        pandoc_timeout: int = PANDOC_TIMEOUT,
    ) -> None:
        self.libreoffice_timeout = libreoffice_timeout
        self.hwp5txt_timeout = hwp5txt_timeout
        self.pandoc_timeout = pandoc_timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def convert(self, file_path: Path) -> dict[str, Any]:
        """Convert an HWP or HWPX file to a Pandoc AST JSON dict.

        Tries LibreOffice first; if that fails or produces no output, falls
        back to ``hwp5txt``.

        Args:
            file_path: Absolute path to the source .hwp or .hwpx file.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            ValueError: If the extension is not supported.
            HWPConversionError: If both conversion strategies fail.
        """
        ext = file_path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"HWPConverter does not support extension '{ext}'. "
                f"Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        if not file_path.exists():
            raise HWPConversionError(f"File not found: {file_path}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                return self._libreoffice_convert(file_path, tmp_path)
            except HWPConversionError as lo_exc:
                logger.warning(
                    "LibreOffice conversion failed for %s (%s); trying hwp5txt fallback",
                    file_path.name,
                    lo_exc,
                )

        try:
            return self._hwp5txt_fallback(file_path)
        except HWPConversionError as fb_exc:
            raise HWPConversionError(
                f"Both conversion strategies failed for {file_path.name}. "
                f"LibreOffice: <see log>; hwp5txt: {fb_exc}"
            ) from fb_exc

    def extract_images(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Extract images embedded in an HWP or HWPX file.

        .hwpx files are ZIP archives; images live under ``BinData/`` or
        ``Contents/`` entries.

        .hwp files are OLE compound documents; the ``BinData`` storage
        contains embedded objects.  ``hwp5`` (the Python library shipped with
        ``hwp5txt``) is used when available; otherwise the method silently
        returns an empty list so the pipeline continues without images.

        Args:
            file_path: Absolute path to the source HWP/HWPX file.
            output_dir: Directory where extracted images are written.

        Returns:
            Sorted list of paths to extracted image files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = file_path.suffix.lower()

        if ext == ".hwpx":
            return self._extract_images_hwpx(file_path, output_dir)
        else:
            return self._extract_images_hwp(file_path, output_dir)

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _libreoffice_convert(
        self, file_path: Path, tmp_dir: Path
    ) -> dict[str, Any]:
        """Convert via LibreOffice headless → DOCX → Pandoc AST JSON.

        Args:
            file_path: Source HWP/HWPX file.
            tmp_dir: Writable scratch directory for LibreOffice output.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            HWPConversionError: If LibreOffice is unavailable, times out, or
                produces no DOCX; or if Pandoc fails.
        """
        if not shutil.which("libreoffice"):
            raise HWPConversionError("libreoffice executable not found in PATH")

        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to", "docx",
            "--outdir", str(tmp_dir),
            str(file_path),
        ]
        logger.debug("Running LibreOffice: %s", " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.libreoffice_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise HWPConversionError(
                f"LibreOffice timed out after {self.libreoffice_timeout}s"
            ) from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode(errors="replace")[:500]
            raise HWPConversionError(
                f"LibreOffice exited with {proc.returncode}: {stderr}"
            )

        # LibreOffice names the output file after the stem of the input.
        docx_path = tmp_dir / f"{file_path.stem}.docx"
        if not docx_path.exists():
            # Some LibreOffice versions lowercase the stem; do a glob search.
            candidates = list(tmp_dir.glob("*.docx"))
            if not candidates:
                raise HWPConversionError(
                    f"LibreOffice did not produce a DOCX in {tmp_dir}"
                )
            docx_path = candidates[0]
            logger.debug("Using LibreOffice output: %s", docx_path.name)

        return self._docx_to_ast(docx_path)

    def _hwp5txt_fallback(self, file_path: Path) -> dict[str, Any]:
        """Extract plain text via hwp5txt and convert to Pandoc AST JSON.

        The plain text is treated as Markdown, which loses HWP formatting but
        preserves paragraph text content.

        Args:
            file_path: Source HWP file.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            HWPConversionError: If hwp5txt is unavailable, times out, or
                returns no usable output; or if Pandoc fails.
        """
        if not shutil.which("hwp5txt"):
            raise HWPConversionError("hwp5txt executable not found in PATH")

        logger.debug("Running hwp5txt on %s", file_path.name)
        try:
            txt_proc = subprocess.run(
                ["hwp5txt", str(file_path)],
                capture_output=True,
                text=True,
                timeout=self.hwp5txt_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise HWPConversionError(
                f"hwp5txt timed out after {self.hwp5txt_timeout}s"
            ) from exc

        if txt_proc.returncode != 0:
            stderr = txt_proc.stderr[:500]
            raise HWPConversionError(
                f"hwp5txt exited with {txt_proc.returncode}: {stderr}"
            )

        plain_text = txt_proc.stdout
        if not plain_text.strip():
            raise HWPConversionError("hwp5txt produced empty output")

        return self._text_to_ast(plain_text)

    # ------------------------------------------------------------------
    # Pandoc wrappers
    # ------------------------------------------------------------------

    def _docx_to_ast(self, docx_path: Path) -> dict[str, Any]:
        """Run ``pandoc <docx> -t json`` and return the parsed AST dict.

        Args:
            docx_path: Path to a DOCX file.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            HWPConversionError: On timeout or non-zero Pandoc exit.
        """
        logger.debug("Converting DOCX to AST: %s", docx_path.name)
        try:
            result = subprocess.run(
                ["pandoc", str(docx_path), "-t", "json"],
                capture_output=True,
                text=True,
                timeout=self.pandoc_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise HWPConversionError(
                f"Pandoc timed out after {self.pandoc_timeout}s"
            ) from exc

        if result.returncode != 0:
            raise HWPConversionError(
                f"Pandoc failed (exit {result.returncode}): {result.stderr[:500]}"
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise HWPConversionError(f"Pandoc returned invalid JSON: {exc}") from exc

    def _text_to_ast(self, text: str) -> dict[str, Any]:
        """Convert plain/Markdown text to a Pandoc AST JSON dict via stdin.

        Args:
            text: Plain text or Markdown source.

        Returns:
            Pandoc AST JSON dict.

        Raises:
            HWPConversionError: On timeout, non-zero exit, or bad JSON.
        """
        logger.debug("Converting plain text to Pandoc AST")
        try:
            result = subprocess.run(
                ["pandoc", "-f", "markdown", "-t", "json"],
                input=text,
                capture_output=True,
                text=True,
                timeout=self.pandoc_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise HWPConversionError(
                f"Pandoc timed out after {self.pandoc_timeout}s"
            ) from exc

        if result.returncode != 0:
            raise HWPConversionError(
                f"Pandoc failed (exit {result.returncode}): {result.stderr[:500]}"
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise HWPConversionError(f"Pandoc returned invalid JSON: {exc}") from exc

    # ------------------------------------------------------------------
    # Image extraction helpers
    # ------------------------------------------------------------------

    def _extract_images_hwpx(
        self, file_path: Path, output_dir: Path
    ) -> list[Path]:
        """Extract images from an HWPX (ZIP-based) file.

        HWPX is a ZIP archive.  Images are stored under ``BinData/`` or
        ``Contents/`` entries with common image extensions.

        Args:
            file_path: Source .hwpx file.
            output_dir: Destination directory for extracted images.

        Returns:
            Sorted list of extracted image paths.
        """
        import zipfile

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf"}
        extracted: list[Path] = []

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for entry in zf.infolist():
                    entry_path = Path(entry.filename)
                    if entry_path.suffix.lower() in image_extensions:
                        # Flatten into output_dir to avoid sub-directory creation
                        dest = output_dir / entry_path.name
                        # Deduplicate filenames if needed
                        if dest.exists():
                            dest = output_dir / f"{entry_path.stem}_{len(extracted)}{entry_path.suffix}"
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
        except zipfile.BadZipFile as exc:
            logger.warning("%s is not a valid ZIP/HWPX file: %s", file_path.name, exc)

        return sorted(extracted)

    def _extract_images_hwp(
        self, file_path: Path, output_dir: Path
    ) -> list[Path]:
        """Extract images from a binary HWP (OLE) file.

        Uses the ``hwp5`` Python package (installed alongside ``hwp5txt``)
        when available.  Falls back to the ``hwp5html`` CLI exporter which
        writes embedded media to disk, then picks up image files from its
        output directory.

        Args:
            file_path: Source .hwp file.
            output_dir: Destination directory for extracted images.

        Returns:
            Sorted list of extracted image paths.
        """
        # Strategy 1: hwp5 Python API
        extracted = self._extract_hwp_via_python_api(file_path, output_dir)
        if extracted:
            return extracted

        # Strategy 2: hwp5html CLI → scrape output directory
        return self._extract_hwp_via_hwp5html(file_path, output_dir)

    def _extract_hwp_via_python_api(
        self, file_path: Path, output_dir: Path
    ) -> list[Path]:
        """Attempt extraction using the hwp5 Python library.

        Returns an empty list when the library is not installed or the
        extraction fails, so the caller can try alternative strategies.
        """
        try:
            import hwp5.filestructure as fs  # type: ignore[import]
        except ImportError:
            logger.debug("hwp5 Python library not available; skipping OLE extraction")
            return []

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf"}
        extracted: list[Path] = []

        try:
            hwp_file = fs.Hwp5File(str(file_path))
            bin_data = hwp_file.get("BinData")
            if bin_data is None:
                return []

            for name in bin_data:
                stem = Path(name)
                if stem.suffix.lower() not in image_extensions:
                    continue
                dest = output_dir / stem.name
                if dest.exists():
                    dest = output_dir / f"{stem.stem}_{len(extracted)}{stem.suffix}"
                try:
                    data = bin_data[name].open().read()
                    dest.write_bytes(data)
                    extracted.append(dest)
                except Exception as exc:
                    logger.warning("Could not extract BinData/%s: %s", name, exc)
        except Exception as exc:
            logger.debug("hwp5 Python API extraction failed for %s: %s", file_path.name, exc)

        return sorted(extracted)

    def _extract_hwp_via_hwp5html(
        self, file_path: Path, output_dir: Path
    ) -> list[Path]:
        """Export HWP to HTML via ``hwp5html``, then collect image files."""
        if not shutil.which("hwp5html"):
            logger.debug("hwp5html not found; skipping HTML-based image extraction")
            return []

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}
        extracted: list[Path] = []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                subprocess.run(
                    ["hwp5html", "--output", str(tmp_path), str(file_path)],
                    capture_output=True,
                    timeout=60,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "hwp5html failed for %s: %s", file_path.name, exc
                )
                return []

            for img_src in sorted(tmp_path.glob("**/*")):
                if img_src.suffix.lower() in image_extensions and img_src.is_file():
                    dest = output_dir / img_src.name
                    if dest.exists():
                        dest = output_dir / f"{img_src.stem}_{len(extracted)}{img_src.suffix}"
                    try:
                        shutil.copy2(img_src, dest)
                        extracted.append(dest)
                    except OSError as exc:
                        logger.warning("Could not copy %s: %s", img_src, exc)

        return sorted(extracted)
