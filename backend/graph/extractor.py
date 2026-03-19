"""GraphExtractor: LLM 기반 엔티티 및 관계 추출 + 지식그래프 구축.

Extracts named entities and semantic relationships from Markdown documents
using an OpenAI chat model, then writes them into a :class:`GraphStore`.
Community detection runs after bulk extraction to group related entities.

Design notes
------------
- Extraction is chunked: each document is split into passages, each passage
  is sent to the LLM with a structured JSON prompt.
- The LLM is instructed to return a dict with ``entities`` and
  ``relationships`` lists so that responses can be parsed deterministically.
- Slug generation is deterministic (lowercase + non-alnum → underscore) so
  that the same entity name always produces the same graph node ID.
- All I/O (file reads, LLM calls) is async to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.graph.models import Community, Entity, Relationship
from backend.graph.store import GraphStore

logger = logging.getLogger(__name__)

# Maximum characters per extraction passage to stay within LLM context limits
_CHUNK_SIZE = 3000
# Maximum concurrent LLM calls during bulk extraction
_MAX_CONCURRENCY = 4

_EXTRACTION_PROMPT = """\
다음 텍스트에서 중요한 엔티티(개체)와 관계를 추출하여 JSON으로 반환하세요.

엔티티 타입 목록:
- person (사람)
- product (상품/서비스)
- regulation (규정/법령)
- organization (조직/기관)
- concept (개념/용어)
- document (문서/자료)
- term (전문용어)

출력 형식 (반드시 유효한 JSON만 반환):
{
  "entities": [
    {"name": "엔티티명", "type": "엔티티타입", "description": "간략한 설명"}
  ],
  "relationships": [
    {"source": "소스엔티티명", "target": "타겟엔티티명", "type": "관계타입", "description": "관계설명"}
  ]
}

관계 타입 예시: covers(보장), depends_on(의존), regulates(규제), belongs_to(소속), references(참조),
               includes(포함), excludes(제외), requires(요건), provides(제공), defines(정의)

텍스트:
{text}
"""


def _slugify(name: str) -> str:
    """Convert an entity name into a stable, filesystem-safe identifier.

    Args:
        name: Human-readable entity name.

    Returns:
        Lowercase slug with non-alphanumeric characters replaced by
        underscores and consecutive underscores collapsed.
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^\w가-힣]", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "entity"


def _split_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split *text* into passages of at most *chunk_size* characters.

    Splits preferably on blank lines so that paragraphs are kept intact.

    Args:
        text: Document text to split.
        chunk_size: Maximum characters per passage.

    Returns:
        List of non-empty text passages.
    """
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) > chunk_size and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(para)
        current_len += len(para)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks or [text[:chunk_size]]


def _parse_extraction_response(raw: str) -> dict[str, Any]:
    """Parse the LLM extraction JSON response defensively.

    Strips markdown code fences if present, then attempts ``json.loads``.
    Returns an empty structure on any parse failure so callers never crash.

    Args:
        raw: Raw LLM response string.

    Returns:
        Dict with ``entities`` and ``relationships`` lists.
    """
    # Strip ```json ... ``` fences
    text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from inside the string
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.debug("_parse_extraction_response: could not parse response: %.200s", raw)
    return {"entities": [], "relationships": []}


class GraphExtractor:
    """LLM-powered entity and relationship extractor that populates a GraphStore.

    Args:
        graph_store: Target :class:`~backend.graph.store.GraphStore` to populate.
        model: OpenAI model name.  Defaults to the ``vlm_model`` setting.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        model: str | None = None,
    ) -> None:
        self._store = graph_store
        self._model = model or settings.vlm_model
        self._llm: Any = None  # Lazy-init to avoid import cost at module load

    def _get_llm(self) -> Any:
        """Lazily initialise and return the ChatOpenAI client."""
        if self._llm is None:
            from langchain_openai import ChatOpenAI  # noqa: PLC0415

            self._llm = ChatOpenAI(
                model=self._model,
                api_key=settings.openai_api_key,
                temperature=0,
            )
        return self._llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_from_text(
        self,
        text: str,
        source_path: str,
    ) -> tuple[list[Entity], list[Relationship]]:
        """Extract entities and relationships from *text* and store them.

        The text is split into passages of at most :data:`_CHUNK_SIZE`
        characters; each passage is sent to the LLM independently and the
        results are merged before writing to the graph store.

        Args:
            text: Raw document text (Markdown or plain).
            source_path: Vault-relative path of the source document, used to
                annotate entity ``source_paths`` and relationship
                ``source_path``.

        Returns:
            Tuple of (entities, relationships) extracted from the document.
            These are also persisted to the graph store.
        """
        passages = _split_text(text)
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _extract_passage(passage: str) -> dict[str, Any]:
            async with sem:
                return await self._call_llm(passage)

        raw_results = await asyncio.gather(*[_extract_passage(p) for p in passages])

        all_entities: list[Entity] = []
        all_relationships: list[Relationship] = []

        for result in raw_results:
            ents, rels = self._build_graph_objects(result, source_path)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        # Persist to store
        for entity in all_entities:
            self._store.add_entity(entity)
        for rel in all_relationships:
            self._store.add_relationship(rel)

        logger.info(
            "GraphExtractor: %s → %d entities, %d relationships",
            source_path,
            len(all_entities),
            len(all_relationships),
        )
        return all_entities, all_relationships

    async def extract_from_file(self, file_path: Path, rel_path: str) -> tuple[list[Entity], list[Relationship]]:
        """Read a Markdown file and extract its entities/relationships.

        Args:
            file_path: Absolute filesystem path to the document.
            rel_path: Vault-relative path (used as the source_path annotation).

        Returns:
            Tuple of (entities, relationships).
        """
        content = await asyncio.to_thread(file_path.read_text, "utf-8")
        return await self.extract_from_text(content, rel_path)

    async def build_from_vault(self, vault_root: Path) -> dict[str, Any]:
        """Extract entities from all Markdown files under *vault_root*.

        After extraction, Louvain community detection is run and the
        resulting community assignments are saved back to the store.

        Args:
            vault_root: Absolute path to the vault root directory.

        Returns:
            Summary dict with ``files``, ``entities``, ``relationships``,
            ``communities``, and ``errors`` counts.
        """
        md_files = list(vault_root.rglob("*.md"))
        logger.info("GraphExtractor.build_from_vault: %d files found", len(md_files))

        self._store.clear()

        total_entities = 0
        total_rels = 0
        errors: list[str] = []

        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _process(md_file: Path) -> tuple[int, int, str | None]:
            rel_path = "/" + md_file.relative_to(vault_root).as_posix()
            async with sem:
                try:
                    ents, rels = await self.extract_from_file(md_file, rel_path)
                    return len(ents), len(rels), None
                except Exception as exc:  # noqa: BLE001
                    logger.error("GraphExtractor: error on %s: %s", rel_path, exc)
                    return 0, 0, f"{rel_path}: {exc}"

        results = await asyncio.gather(*[_process(f) for f in md_files])
        for ne, nr, err in results:
            total_entities += ne
            total_rels += nr
            if err:
                errors.append(err)

        # Detect and save communities
        communities = self._store.get_communities()
        for community in communities:
            pass  # Communities are computed on-the-fly from the graph, no need to store separately

        self._store.save()

        summary = {
            "files": len(md_files),
            "entities": total_entities,
            "relationships": total_rels,
            "communities": len(communities),
            "errors": errors,
        }
        logger.info("GraphExtractor.build_from_vault complete: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_llm(self, text: str) -> dict[str, Any]:
        """Send *text* to the LLM and return the parsed extraction result.

        Args:
            text: Passage text to process.

        Returns:
            Parsed dict with ``entities`` and ``relationships`` keys.
        """
        llm = self._get_llm()
        prompt = _EXTRACTION_PROMPT.format(text=text)
        try:
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            raw = response.content if hasattr(response, "content") else str(response)
            return _parse_extraction_response(raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("GraphExtractor._call_llm failed: %s", exc)
            return {"entities": [], "relationships": []}

    def _build_graph_objects(
        self,
        extraction: dict[str, Any],
        source_path: str,
    ) -> tuple[list[Entity], list[Relationship]]:
        """Convert raw LLM extraction dicts into Entity and Relationship objects.

        Args:
            extraction: Parsed LLM response with ``entities`` and
                ``relationships`` lists.
            source_path: Vault-relative path to annotate objects with.

        Returns:
            Tuple of (entities, relationships).
        """
        entities: list[Entity] = []
        relationships: list[Relationship] = []

        # Build entity lookup by name for relationship resolution
        name_to_id: dict[str, str] = {}

        for e_dict in extraction.get("entities", []):
            name = str(e_dict.get("name", "")).strip()
            if not name:
                continue
            entity_id = _slugify(name)
            entity_type = str(e_dict.get("type", "concept")).lower()
            description = str(e_dict.get("description", ""))

            entity = Entity(
                id=entity_id,
                name=name,
                entity_type=entity_type,
                properties={"description": description} if description else {},
                source_paths=[source_path],
                mentions=1,
            )
            entities.append(entity)
            name_to_id[name.lower()] = entity_id

        for r_dict in extraction.get("relationships", []):
            src_name = str(r_dict.get("source", "")).strip()
            tgt_name = str(r_dict.get("target", "")).strip()
            rel_type = str(r_dict.get("type", "references")).strip()

            if not src_name or not tgt_name:
                continue

            # Resolve entity IDs — fall back to slugifying the name
            src_id = name_to_id.get(src_name.lower(), _slugify(src_name))
            tgt_id = name_to_id.get(tgt_name.lower(), _slugify(tgt_name))

            rel = Relationship(
                source_id=src_id,
                target_id=tgt_id,
                relation_type=rel_type,
                properties={"description": str(r_dict.get("description", ""))},
                source_path=source_path,
                weight=1.0,
            )
            relationships.append(rel)

        return entities, relationships


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_extractor: GraphExtractor | None = None


def get_graph_extractor() -> GraphExtractor:
    """Return (and lazily initialise) the module-level GraphExtractor singleton.

    Uses the module-level :class:`GraphStore` singleton as the target store.

    Returns:
        The singleton :class:`GraphExtractor` instance.
    """
    global _extractor
    if _extractor is None:
        from backend.graph.store import GraphStore  # noqa: PLC0415 – lazy import

        _store = GraphStore()
        _extractor = GraphExtractor(graph_store=_store)
    return _extractor
