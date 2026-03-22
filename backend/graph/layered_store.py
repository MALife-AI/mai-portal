"""Layered Knowledge Graph: 베이스(공용) + 사용자별 개인 그래프 레이어 관리.

구조:
  .graph/
    base.json             ← 관리자가 Shared/ 문서에서 빌드 (공용)
    users/
      admin01.json        ← admin01의 Private 문서에서 추출
      analyst01.json      ← analyst01의 Private 문서에서 추출

조회 시 베이스 + 해당 사용자의 개인 그래프를 합쳐서 반환합니다.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import networkx as nx

from backend.config import settings
from backend.graph.store import GraphStore
from backend.graph.models import Entity, Relationship

logger = logging.getLogger(__name__)

_GRAPH_ROOT = settings.vault_root / ".graph"


class LayeredGraphStore:
    """베이스 + 사용자별 그래프 레이어를 관리하는 래퍼."""

    def __init__(self) -> None:
        self._base_path = _GRAPH_ROOT / "base.json"
        self._users_dir = _GRAPH_ROOT / "users"
        self._users_dir.mkdir(parents=True, exist_ok=True)

        # 베이스 그래프 로드
        self._base = GraphStore(persist_path=self._base_path)

        # 호환성: 기존 knowledge_graph.json이 있고 base.json이 없으면 마이그레이션
        legacy_path = _GRAPH_ROOT / "knowledge_graph.json"
        if legacy_path.exists() and not self._base_path.exists():
            import shutil
            shutil.copy2(legacy_path, self._base_path)
            self._base = GraphStore(persist_path=self._base_path)
            logger.info("Migrated legacy knowledge_graph.json → base.json")

        # 사용자별 그래프 캐시
        self._user_stores: dict[str, GraphStore] = {}

    # ------------------------------------------------------------------
    # 그래프 접근
    # ------------------------------------------------------------------

    @property
    def base(self) -> GraphStore:
        """베이스(공용) 그래프."""
        return self._base

    def user_store(self, user_id: str) -> GraphStore:
        """사용자 개인 그래프. 없으면 빈 그래프 생성."""
        if user_id not in self._user_stores:
            path = self._users_dir / f"{user_id}.json"
            self._user_stores[user_id] = GraphStore(persist_path=path)
        return self._user_stores[user_id]

    def get_store_for_path(self, rel_path: str, user_id: str) -> GraphStore:
        """문서 경로에 따라 적절한 그래프 반환.

        Private/{user_id}/... → 개인 그래프
        그 외 → 베이스 그래프
        """
        parts = rel_path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "Private":
            doc_owner = parts[1]
            return self.user_store(doc_owner)
        return self._base

    # ------------------------------------------------------------------
    # 병합 조회
    # ------------------------------------------------------------------

    def merged_store(self, user_id: str) -> GraphStore:
        """베이스 + 사용자 그래프를 합친 임시 GraphStore 반환.

        조회 전용으로 사용. 이 객체에 write하면 안 됨.
        """
        merged = GraphStore.__new__(GraphStore)
        merged._path = Path("/dev/null")
        merged._graph = nx.DiGraph()

        # 베이스 복사
        merged._graph = nx.compose(merged._graph, self._base._graph)

        # 사용자 그래프 합성
        user_store = self.user_store(user_id)
        if user_store._graph.number_of_nodes() > 0:
            merged._graph = nx.compose(merged._graph, user_store._graph)

        return merged

    # ------------------------------------------------------------------
    # 통계
    # ------------------------------------------------------------------

    def get_layer_stats(self, user_id: str) -> dict[str, Any]:
        """레이어별 통계."""
        user_g = self.user_store(user_id)
        return {
            "base": {
                "nodes": self._base._graph.number_of_nodes(),
                "edges": self._base._graph.number_of_edges(),
            },
            "personal": {
                "nodes": user_g._graph.number_of_nodes(),
                "edges": user_g._graph.number_of_edges(),
            },
            "merged": {
                "nodes": self._base._graph.number_of_nodes() + user_g._graph.number_of_nodes(),
                "edges": self._base._graph.number_of_edges() + user_g._graph.number_of_edges(),
            },
        }

    def list_user_graphs(self) -> list[dict[str, Any]]:
        """모든 사용자 그래프 목록."""
        result = []
        for path in sorted(self._users_dir.glob("*.json")):
            uid = path.stem
            store = self.user_store(uid)
            result.append({
                "user_id": uid,
                "nodes": store._graph.number_of_nodes(),
                "edges": store._graph.number_of_edges(),
            })
        return result


# 싱글톤
_layered_store: LayeredGraphStore | None = None


def get_layered_store() -> LayeredGraphStore:
    global _layered_store
    if _layered_store is None:
        _layered_store = LayeredGraphStore()
    return _layered_store
