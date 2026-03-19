"""Vision LLM Processor: 이미지를 분석하여 표/다이어그램 분류 및 변환."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


class VLMProcessor:
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
