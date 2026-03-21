"""
Universal Document Ingestion Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HWP / PDF / PPTX / DOCX → Pandoc AST(IR) → Multimodal VLM → Sanitized GFM Markdown

Architecture:
  Raw File
    ↓
  Format Converter (Pandoc / Marker)
    ↓
  Pandoc AST (Unified IR as JSON)
    ↓
  Image Extractor → VLM Processor
    ↓  (table image → MD table, diagram → caption)
  AST Reassembler
    ↓
  Markdown Post-Processor (GFM sanitize)
    ↓
  Final .md + /assets/{doc}/
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.ingestion.converters import HWPConverter, OfficeConverter, PDFConverter
from backend.ingestion.pandoc_ast import (
    ast_to_markdown,
    extract_images_from_ast,
    inject_table_into_ast,
    inject_caption_into_ast,
)
from backend.ingestion.vlm_processor import get_image_processor
from backend.ingestion.markdown_post import post_process
from backend.core.vault import write_document

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """이기종 문서를 규격화된 마크다운으로 변환하는 통합 파이프라인."""

    SUPPORTED_EXTENSIONS = {".pdf", ".hwp", ".hwpx", ".pptx", ".docx", ".doc"}

    def __init__(self) -> None:
        self.vlm = get_image_processor()
        self._pdf_converter = PDFConverter()
        self._hwp_converter = HWPConverter()
        self._office_converter = OfficeConverter()

    async def ingest(
        self,
        file_path: Path,
        *,
        user_id: str,
        dest_rel: str | None = None,
    ) -> str:
        """파일을 변환하여 Vault에 저장하고 상대 경로를 반환."""
        ext = file_path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported format: {ext}")

        doc_name = file_path.stem
        assets_dir = settings.vault_root / "assets" / doc_name
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Format → Pandoc AST JSON (IR)
        ast_json = await self._to_pandoc_ast(file_path, ext, assets_dir)

        # Step 2: 이미지 추출 + VLM 분석
        ast_json = await self._process_images(ast_json, assets_dir, doc_name)

        # Step 3: AST → Markdown
        raw_md = await ast_to_markdown(ast_json)

        # Step 4: Post-processing (GFM 정규화)
        clean_md = post_process(raw_md)

        # Step 5: Vault 저장 + Git 커밋
        rel_path = dest_rel or f"Shared/{doc_name}.md"
        await write_document(
            rel_path,
            clean_md,
            user_id=user_id,
            extra_meta={"source_format": ext, "ingested": True},
        )
        return rel_path

    async def _to_pandoc_ast(
        self, file_path: Path, ext: str, assets_dir: Path | None = None,
    ) -> dict[str, Any]:
        """포맷별 변환기를 거쳐 Pandoc AST JSON을 반환."""
        if ext == ".pdf":
            return await self._pdf_to_ast(file_path)
        elif ext in {".hwp", ".hwpx"}:
            return await self._hwp_to_ast(file_path)
        else:
            # DOCX, PPTX — Pandoc 직접 변환 (media를 assets_dir에 추출)
            return await self._pandoc_native(file_path, assets_dir)

    async def _pandoc_native(
        self, file_path: Path, media_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Pandoc이 직접 지원하는 포맷 → AST JSON.

        Delegates to :class:`~backend.ingestion.converters.OfficeConverter`.
        """
        return await asyncio.to_thread(
            self._office_converter.convert, file_path, media_dir=media_dir,
        )

    async def _pdf_to_ast(self, file_path: Path) -> dict[str, Any]:
        """PDF → 텍스트 확인 → pdf2docx 또는 OCR → Pandoc AST.

        1. pdftotext로 텍스트 존재 여부 확인
        2. 텍스트 충분 → pdf2docx → DOCX → Pandoc AST
        3. 텍스트 부족 (스캔 문서) → OCR(pdftoppm+tesseract) → Pandoc AST
        """
        import subprocess
        import sys
        import tempfile

        # 텍스트 존재 여부 확인 (빠름)
        is_scanned = False
        try:
            r = await asyncio.to_thread(
                subprocess.run,
                ["pdftotext", str(file_path), "-"],
                capture_output=True, text=True, timeout=15,
            )
            korean_chars = sum(1 for c in r.stdout if '\uac00' <= c <= '\ud7a3')
            is_scanned = korean_chars < 50
        except Exception:
            is_scanned = True

        if is_scanned:
            # OCR 경로
            import json as _json
            md_text = await self._ocr_pdf(file_path)
            r = await asyncio.to_thread(
                subprocess.run,
                ["pandoc", "-f", "markdown", "-t", "json"],
                input=md_text, capture_output=True, text=True, timeout=60,
            )
            return _json.loads(r.stdout)

        # 텍스트 PDF → pdf2docx (별도 프로세스, 120초 타임아웃)
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "converted.docx"
            script = (
                "import sys; from pdf2docx import Converter; "
                "cv = Converter(sys.argv[1]); cv.convert(sys.argv[2]); cv.close()"
            )
            proc = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-c", script, str(file_path), str(docx_path)],
                capture_output=True, timeout=120,
            )

            if proc.returncode != 0 or not docx_path.exists():
                raise RuntimeError(f"pdf2docx failed: {proc.stderr[:200]}")

            return await asyncio.to_thread(
                self._office_converter.convert, docx_path,
            )

    async def _ocr_pdf(self, file_path: Path) -> str:
        """스캔 PDF → OCR(pdftoppm + tesseract) → 마크다운 텍스트."""
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # PDF → PNG (200dpi)
            await asyncio.to_thread(
                subprocess.run,
                ["pdftoppm", "-png", "-r", "200", str(file_path), str(tmp_path / "page")],
                capture_output=True, timeout=300,
            )

            pages = sorted(tmp_path.glob("page-*.png"))
            if not pages:
                raise RuntimeError("pdftoppm produced no output")

            all_text: list[str] = []
            for i, page_img in enumerate(pages, 1):
                r = await asyncio.to_thread(
                    subprocess.run,
                    ["tesseract", str(page_img), "stdout", "-l", "kor+eng", "--psm", "6"],
                    capture_output=True, text=True, timeout=60,
                )
                text = r.stdout.strip()
                if text:
                    all_text.append(f"<!-- page:{i} -->\n{text}")

            if not all_text:
                raise RuntimeError("OCR produced no text")

            return f"# {file_path.stem}\n\n" + "\n\n".join(all_text)

    async def _hwp_to_ast(self, file_path: Path) -> dict[str, Any]:
        """HWP → (LibreOffice → DOCX / hwp5txt fallback) → Pandoc AST.

        Delegates to :class:`~backend.ingestion.converters.HWPConverter`.
        """
        return await asyncio.to_thread(self._hwp_converter.convert, file_path)

    async def _process_images(
        self,
        ast_json: dict[str, Any],
        assets_dir: Path,
        doc_name: str,
    ) -> dict[str, Any]:
        """AST에서 이미지를 추출하고 VLM 분석 후 AST를 재조립."""
        images = extract_images_from_ast(ast_json)
        if not images:
            return ast_json

        tasks = []
        for img_info in images:
            src_path = Path(img_info["src"])
            # 상대 경로인 경우 assets_dir 기준으로 해석 (pandoc --extract-media=. 출력)
            if not src_path.is_absolute():
                src_path = assets_dir / src_path
            if src_path.exists():
                dest = assets_dir / src_path.name
                if src_path != dest:
                    shutil.copy2(src_path, dest)
                img_info["saved_path"] = dest
                tasks.append(self.vlm.analyze_image(dest))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for img_info, result in zip(images, results):
            if isinstance(result, Exception):
                logger.error("VLM failed for %s: %s", img_info["src"], result)
                continue

            if result["type"] == "table":
                ast_json = inject_table_into_ast(
                    ast_json, img_info["node_id"], result["markdown_table"]
                )
            elif result["type"] == "text":
                # OCR 추출 텍스트로 이미지 노드 교체
                ast_json = inject_table_into_ast(
                    ast_json, img_info["node_id"], result["caption"]
                )
            else:
                ast_json = inject_caption_into_ast(
                    ast_json, img_info["node_id"], result["caption"]
                )

        return ast_json
