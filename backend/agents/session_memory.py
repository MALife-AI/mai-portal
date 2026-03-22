"""Session Memory: 대화 세션별 메모리 관리.

스레드(세션) 단위로 중요 정보를 메모 형태로 저장하고,
이후 대화에서 recall하여 LLM 컨텍스트에 주입합니다.

저장 구조:
  data/memories/{thread_id}/
    index.json   ← [{id, summary, category, timestamp}]
    001.md       ← 개별 메모 내용
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)

MEMORIES_DIR = Path(settings.vault_root).parent / "data" / "memories"


class SessionMemory:
    """스레드별 메모리 관리자."""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        self._dir = MEMORIES_DIR / self._safe_dir_name(thread_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"

    @staticmethod
    def _safe_dir_name(thread_id: str) -> str:
        """thread_id를 안전한 디렉토리명으로 변환."""
        return thread_id.replace("/", "_").replace(":", "_").replace(" ", "_")[:100]

    def _load_index(self) -> list[dict[str, Any]]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_index(self, index: list[dict[str, Any]]) -> None:
        self._index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, summary: str, content: str, category: str = "general") -> dict[str, Any]:
        """메모를 저장합니다.

        Args:
            summary: 한 줄 요약 (인덱스에 표시)
            content: 상세 내용
            category: 분류 (customer_info, product_choice, conversation_context 등)

        Returns:
            저장된 메모 메타데이터
        """
        index = self._load_index()
        memo_id = len(index) + 1
        memo_filename = f"{memo_id:03d}.md"
        timestamp = datetime.now(timezone.utc).isoformat()

        # 메모 파일 저장
        memo_path = self._dir / memo_filename
        memo_content = (
            f"# {summary}\n\n"
            f"- 시점: {timestamp}\n"
            f"- 분류: {category}\n\n"
            f"{content}\n"
        )
        memo_path.write_text(memo_content, encoding="utf-8")

        # 인덱스 업데이트
        entry = {
            "id": memo_id,
            "file": memo_filename,
            "summary": summary,
            "category": category,
            "timestamp": timestamp,
        }
        index.append(entry)
        self._save_index(index)

        logger.info("Memory saved: thread=%s, id=%d, summary=%s", self.thread_id, memo_id, summary)
        return entry

    def recall_all(self) -> str:
        """모든 메모의 인덱스를 반환합니다."""
        index = self._load_index()
        if not index:
            return "저장된 기억이 없습니다."

        lines = ["## 이 대화의 기억 목록\n"]
        for entry in index:
            lines.append(
                f"- [{entry['id']}] {entry['summary']} "
                f"({entry['category']}, {entry['timestamp'][:16]})"
            )
        return "\n".join(lines)

    def recall_by_id(self, memo_id: int) -> str:
        """특정 메모의 상세 내용을 반환합니다."""
        index = self._load_index()
        entry = next((e for e in index if e["id"] == memo_id), None)
        if not entry:
            return f"메모 #{memo_id}를 찾을 수 없습니다."

        memo_path = self._dir / entry["file"]
        if not memo_path.exists():
            return f"메모 파일이 존재하지 않습니다: {entry['file']}"

        return memo_path.read_text(encoding="utf-8")

    def recall_by_keyword(self, keyword: str) -> str:
        """키워드로 메모를 검색합니다."""
        index = self._load_index()
        results: list[str] = []

        for entry in index:
            # 인덱스 summary에서 검색
            if keyword.lower() in entry["summary"].lower():
                memo_path = self._dir / entry["file"]
                if memo_path.exists():
                    content = memo_path.read_text(encoding="utf-8")
                    results.append(f"### 메모 #{entry['id']}: {entry['summary']}\n{content}")
                continue

            # 파일 내용에서 검색
            memo_path = self._dir / entry["file"]
            if memo_path.exists():
                content = memo_path.read_text(encoding="utf-8")
                if keyword.lower() in content.lower():
                    results.append(f"### 메모 #{entry['id']}: {entry['summary']}\n{content}")

        if not results:
            return f"'{keyword}'와 관련된 기억을 찾지 못했습니다."

        return "\n\n".join(results)

    def get_context_summary(self, max_entries: int = 5) -> str:
        """최근 메모를 요약하여 시스템 프롬프트에 주입할 컨텍스트를 생성합니다."""
        index = self._load_index()
        if not index:
            return ""

        recent = index[-max_entries:]
        lines = ["[이전 대화에서 기억한 정보]"]
        for entry in recent:
            memo_path = self._dir / entry["file"]
            if memo_path.exists():
                content = memo_path.read_text(encoding="utf-8")
                # 첫 3줄만 (제목 + 핵심)
                preview = "\n".join(content.strip().splitlines()[:3])
                lines.append(f"- {entry['summary']}: {preview}")
            else:
                lines.append(f"- {entry['summary']}")

        return "\n".join(lines)
