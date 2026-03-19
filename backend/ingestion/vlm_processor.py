"""Vision Processor: 이미지를 분석하여 표/다이어그램 분류 및 변환.

로컬 모드(img2table + Tesseract)를 우선 사용하고,
API 키가 설정된 경우에만 VLM(OpenAI Vision)으로 폴백한다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


class LocalTableExtractor:
    """img2table + Tesseract OCR 기반 로컬 표 추출기. LLM 불필요."""

    def __init__(self, langs: str = "kor+eng") -> None:
        self._langs = langs

    async def analyze_image(self, image_path: Path) -> dict[str, Any]:
        """이미지에서 표를 감지하고 GFM 마크다운으로 변환."""
        return await asyncio.to_thread(self._extract, image_path)

    def _extract(self, image_path: Path) -> dict[str, Any]:
        # 1) 표 감지 시도
        table_md = self._try_table(image_path)
        if table_md:
            return {
                "type": "table",
                "markdown_table": table_md,
                "caption": "",
            }

        # 2) 범용 OCR 텍스트 추출
        text = self._try_ocr(image_path)
        if text:
            return {
                "type": "text",
                "markdown_table": "",
                "caption": text,
            }

        # 3) 둘 다 실패
        return {
            "type": "diagram",
            "markdown_table": "",
            "caption": image_path.stem,
        }

    def _try_table(self, image_path: Path) -> str:
        """img2table로 표 감지 및 GFM 변환. 실패 시 빈 문자열."""
        try:
            from img2table.document import Image as Img2TableImage
            from img2table.ocr import TesseractOCR

            ocr = TesseractOCR(lang=self._langs)
            doc = Img2TableImage(src=str(image_path))
            tables = doc.extract_tables(ocr=ocr, borderless_tables=True)

            if not tables:
                return ""

            best = max(tables, key=lambda t: len(t.content.values()))
            df = best.df
            if df is None or df.empty:
                return ""

            return self._df_to_gfm(df)
        except Exception as exc:
            logger.debug("img2table failed for %s: %s", image_path.name, exc)
            return ""

    def _try_ocr(self, image_path: Path) -> str:
        """Tesseract OCR로 텍스트 추출. 실패 시 빈 문자열."""
        import subprocess

        try:
            result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", self._langs, "--psm", "6"],
                capture_output=True, text=True, timeout=30,
            )
            text = result.stdout.strip()
            return text if len(text) > 5 else ""
        except Exception as exc:
            logger.debug("Tesseract OCR failed for %s: %s", image_path.name, exc)
            return ""

    @staticmethod
    def _df_to_gfm(df: Any) -> str:
        """pandas DataFrame → GFM 마크다운 테이블."""
        headers = [str(c) for c in df.columns]
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for _, row in df.iterrows():
            cells = [str(v).replace("|", "\\|").replace("\n", " ") for v in row]
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)


class VLMProcessor:
    """OpenAI Vision API 기반 이미지 분석기."""

    TABLE_PROMPT = (
        "이 이미지가 표(table)인지 도표/다이어그램(diagram)인지 판별하세요.\n"
        "표라면 type='table'로 응답하고 Markdown 표로 정확히 복원하세요.\n"
        "도표/다이어그램이라면 type='diagram'으로 응답하고 의미를 한국어로 요약하세요.\n"
        'JSON 형식으로만 응답: {"type": "table"|"diagram", "markdown_table": "...", "caption": "..."}'
    )

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    async def analyze_image(self, image_path: Path) -> dict[str, Any]:
        """이미지를 VLM으로 분석하여 표 복원 또는 캡션 생성."""
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        mime = "image/png" if image_path.suffix == ".png" else "image/jpeg"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": self.TABLE_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                                },
                            ],
                        }
                    ],
                    "max_tokens": 2000,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        return {
            "type": result.get("type", "diagram"),
            "markdown_table": result.get("markdown_table", ""),
            "caption": result.get("caption", ""),
        }


def get_image_processor() -> LocalTableExtractor | VLMProcessor:
    """API 키 유효 여부에 따라 적절한 프로세서를 반환."""
    api_key = settings.openai_api_key
    if api_key and not api_key.startswith("sk-..."):
        logger.info("Using VLM (OpenAI Vision) for image processing")
        return VLMProcessor(model=settings.vlm_model)
    logger.info("Using local table extractor (img2table + Tesseract)")
    return LocalTableExtractor()
