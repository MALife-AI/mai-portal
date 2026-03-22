"""Knowledge Graph Builder: Vault 전체 문서에서 그래프 구축."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiofiles
from git import Repo, InvalidGitRepositoryError

from backend.graph.extractor import GraphExtractor
from backend.graph.models import Entity, Relationship
from backend.graph.store import GraphStore

logger = logging.getLogger(__name__)

# Maximum number of documents processed concurrently to balance throughput vs.
# OpenAI rate limits.
_MAX_CONCURRENCY = 4


class GraphBuilder:
    """Orchestrates vault-wide knowledge graph construction.

    Walks all Markdown files in a vault, delegates per-document extraction
    to :class:`~backend.graph.extractor.GraphExtractor`, and persists the
    resulting graph via :class:`~backend.graph.store.GraphStore`.

    Args:
        store: Destination graph store.
        extractor: Entity/relationship extractor to use for each document.
    """

    def __init__(self, store: GraphStore, extractor: GraphExtractor) -> None:
        self._store = store
        self._extractor = extractor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build_from_vault(
        self,
        vault_root: Path,
        iam_path: Path | None = None,
    ) -> dict[str, Any]:
        """Build the knowledge graph by processing every Markdown file in *vault_root*.

        Processing steps for each file:
        1. Read the file content.
        2. Extract entities and relationships via the LLM extractor.
        3. Extract structural relationships from Obsidian ``[[wikilinks]]``.
        4. Upsert all findings into the graph store.

        The store is saved to disk once after all files have been processed.

        Args:
            vault_root: Absolute path to the vault root directory.
            iam_path: Optional sub-directory to restrict processing to.
                When provided only files under *iam_path* are processed.

        Returns:
            Stats dict with keys: ``processed``, ``entities_added``,
            ``relationships_added``, ``errors``.
        """
        search_root = iam_path if iam_path and iam_path.is_dir() else vault_root
        md_files = [
            p for p in search_root.rglob("*.md")
            if p.is_file() and not p.name.startswith(".")
        ]
        logger.info(
            "GraphBuilder.build_from_vault: discovered %d Markdown files under %s",
            len(md_files),
            search_root,
        )

        total_processed = 0
        total_entities = 0
        total_relationships = 0
        errors: list[str] = []

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _process_file(md_file: Path) -> tuple[int, int, str | None]:
            rel_path = md_file.relative_to(vault_root).as_posix()
            async with semaphore:
                try:
                    content = await _read_file(md_file)
                    ne, nr = await self.build_from_document(content, rel_path)
                    return ne, nr, None
                except Exception as exc:  # noqa: BLE001
                    logger.error("GraphBuilder: failed on %s: %s", rel_path, exc)
                    return 0, 0, f"{rel_path}: {exc}"

        results = await asyncio.gather(*[_process_file(f) for f in md_files])

        for ne, nr, err in results:
            total_processed += 1
            total_entities += ne
            total_relationships += nr
            if err:
                errors.append(err)

        self._store.save()

        stats: dict[str, Any] = {
            "processed": total_processed,
            "entities_added": total_entities,
            "relationships_added": total_relationships,
            "errors": errors,
        }
        logger.info("GraphBuilder.build_from_vault complete: %s", stats)
        return stats

    async def build_from_document(
        self,
        content: str,
        source_path: str,
    ) -> tuple[int, int]:
        """Process a single document and integrate findings into the existing graph.

        This method does **not** clear the store first, so it is safe to call
        incrementally as new documents arrive.

        Args:
            content: Raw Markdown content (may include YAML frontmatter).
            source_path: Vault-relative path of the document.

        Returns:
            Tuple of ``(entities_added, relationships_added)``.
        """
        # --- LLM entity/relationship extraction ---
        existing_names = _collect_existing_entity_names(self._store)
        entities, relationships = await self._extractor.extract_from_document(
            content=content,
            source_path=source_path,
            existing_entities=existing_names,
        )

        # --- Structural wikilink extraction ---
        wikilink_rels: list[Relationship] = await self._extractor.extract_from_wikilinks(
            content=content,
            source_path=source_path,
        )

        # --- Upsert into store ---
        for entity in entities:
            self._store.add_entity(entity)
        for rel in list(relationships) + wikilink_rels:
            self._store.add_relationship(rel)

        entities_added = len(entities)
        relationships_added = len(relationships) + len(wikilink_rels)

        logger.debug(
            "build_from_document(%s): +%d entities, +%d relationships (+%d wikilinks)",
            source_path,
            entities_added,
            len(relationships),
            len(wikilink_rels),
        )
        return entities_added, relationships_added

    async def rebuild(self, vault_root: Path) -> dict[str, Any]:
        """Clear the graph store and rebuild it from scratch.

        This is equivalent to calling :meth:`build_from_vault` on a fresh
        store.  Useful when the extraction model or prompts have changed and
        you want a clean slate.

        Args:
            vault_root: Absolute path to the vault root directory.

        Returns:
            Stats dict (same structure as :meth:`build_from_vault`).
        """
        logger.info("GraphBuilder.rebuild: clearing graph and rebuilding from %s", vault_root)
        self._store.clear()
        return await self.build_from_vault(vault_root)

    async def build_all_versions(
        self,
        vault_root: Path,
        max_versions_per_file: int = 10,
    ) -> dict[str, Any]:
        """모든 문서의 git 히스토리 버전을 그래프에 인덱싱합니다.

        각 버전의 엔티티에는 version_hash, version_date, version_label 속성이
        추가되어, 같은 문서의 서로 다른 시점 내용을 구분할 수 있습니다.

        현재(HEAD) 버전은 build_from_vault()에서 이미 처리되므로,
        이 메서드는 과거 버전만 추가로 인덱싱합니다.

        Args:
            vault_root: vault 루트 경로.
            max_versions_per_file: 파일당 최대 과거 버전 수.

        Returns:
            처리 통계 dict.
        """
        try:
            repo = Repo(vault_root, search_parent_directories=True)
        except InvalidGitRepositoryError:
            logger.warning("Not a git repo — skipping version indexing")
            return {"processed": 0, "versions_indexed": 0, "errors": []}

        md_files = [
            p for p in vault_root.rglob("*.md")
            if p.is_file() and not p.name.startswith(".")
        ]

        total_versions = 0
        errors: list[str] = []
        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _process_versions(md_file: Path) -> int:
            rel_path = md_file.relative_to(vault_root).as_posix()
            versions_added = 0

            async with semaphore:
                try:
                    commits = list(repo.iter_commits(paths=rel_path, max_count=max_versions_per_file + 1))
                except Exception:
                    return 0

                # 첫 번째(HEAD)는 이미 현재 버전으로 인덱싱됨 → 건너뜀
                past_commits = commits[1:] if len(commits) > 1 else []

                for commit in past_commits:
                    try:
                        content = await asyncio.to_thread(
                            lambda c=commit: repo.git.show(f"{c.hexsha}:{rel_path}")
                        )
                        commit_date = commit.committed_datetime.strftime("%Y-%m-%d")
                        commit_hash = commit.hexsha[:8]
                        version_source = f"{rel_path}@{commit_hash}"

                        # 버전별로 엔티티 추출
                        existing_names = _collect_existing_entity_names(self._store)
                        entities, relationships = await self._extractor.extract_from_document(
                            content=content,
                            source_path=version_source,
                            existing_entities=existing_names,
                        )

                        # 버전 메타데이터를 각 엔티티에 주입
                        for entity in entities:
                            entity.properties["version_hash"] = commit_hash
                            entity.properties["version_date"] = commit_date
                            entity.properties["version_label"] = f"{commit_date} ({commit_hash})"
                            entity.properties["is_historical"] = True
                            entity.properties["version_message"] = commit.message.strip()[:100]
                            self._store.add_entity(entity)

                        for rel in relationships:
                            rel.properties["version_hash"] = commit_hash
                            rel.properties["version_date"] = commit_date
                            self._store.add_relationship(rel)

                        versions_added += 1
                    except Exception as exc:
                        errors.append(f"{rel_path}@{commit.hexsha[:8]}: {exc}")

            return versions_added

        results = await asyncio.gather(*[_process_versions(f) for f in md_files])
        total_versions = sum(results)

        self._store.save()

        stats = {
            "processed": len(md_files),
            "versions_indexed": total_versions,
            "errors": errors,
        }
        logger.info("build_all_versions complete: %s", stats)
        return stats

    async def rebuild_with_versions(self, vault_root: Path) -> dict[str, Any]:
        """그래프를 클리어하고 현재 + 전체 버전으로 재구축합니다."""
        logger.info("GraphBuilder.rebuild_with_versions: %s", vault_root)
        self._store.clear()

        # 1) 현재(HEAD) 버전 인덱싱
        current_stats = await self.build_from_vault(vault_root)

        # 2) 과거 버전 인덱싱
        version_stats = await self.build_all_versions(vault_root)

        return {
            "processed": current_stats["processed"],
            "entities_added": current_stats["entities_added"],
            "relationships_added": current_stats["relationships_added"],
            "versions_indexed": version_stats["versions_indexed"],
            "errors": current_stats["errors"] + version_stats["errors"],
        }


# ---------------------------------------------------------------------------
# Module-level singleton & helpers
# ---------------------------------------------------------------------------

def _collect_existing_entity_names(store: GraphStore) -> list[str]:
    """Return a deduplicated list of entity names already present in *store*.

    Used to seed the entity-resolution hint sent to the LLM so it prefers
    reusing known entity names over coining duplicates.

    Args:
        store: Graph store to inspect.

    Returns:
        List of entity display names (up to 200 to keep prompts manageable).
    """
    stats = store.get_stats()
    if stats["node_count"] == 0:
        return []
    # Retrieve a broad search with an empty-ish query; rapidfuzz WRatio
    # against "" will rank everything low but still return results.
    entities = store.search_entities("", limit=200)
    return [e.name for e in entities]


async def _read_file(path: Path) -> str:
    """Asynchronously read a UTF-8 text file.

    Args:
        path: Absolute path to the file.

    Returns:
        File content as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
        UnicodeDecodeError: If the file is not valid UTF-8.
    """
    async with aiofiles.open(path, encoding="utf-8") as fh:
        return await fh.read()


_builder: GraphBuilder | None = None


def get_graph_builder() -> GraphBuilder:
    """Return (and lazily initialise) the module-level :class:`GraphBuilder` singleton.

    The builder shares the same store and extractor singletons used
    throughout the backend so all callers operate on the same graph state.

    Returns:
        The singleton :class:`GraphBuilder` instance.
    """
    global _builder
    if _builder is None:
        from backend.graph.extractor import get_graph_extractor  # noqa: PLC0415
        from backend.graph.store import GraphStore  # noqa: PLC0415

        store = GraphStore()
        extractor = get_graph_extractor()
        _builder = GraphBuilder(store=store, extractor=extractor)
    return _builder
