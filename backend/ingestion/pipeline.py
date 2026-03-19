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
        rel_path = dest_rel or f"Public/{doc_name}.md"
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
        """PDF → Marker(Layout Analysis) → Markdown → Pandoc AST.

        Delegates to :class:`~backend.ingestion.converters.PDFConverter`.
        """
        return await asyncio.to_thread(self._pdf_converter.convert, file_path)

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
            else:
                ast_json = inject_caption_into_ast(
                    ast_json, img_info["node_id"], result["caption"]
                )

        return ast_json
