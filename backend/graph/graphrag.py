"""GraphRAG Engine: 벡터 검색 + 지식그래프 순회 결합 검색.

GraphRAG combines two complementary retrieval strategies:

1. **Vector search** — dense semantic search via ChromaDB finds document
   chunks whose embedding is close to the query.

2. **Graph traversal** — named entities mentioned in the query are matched
   against the knowledge graph; their neighbourhoods are traversed to surface
   related entities, relationships, and community summaries that provide
   broader context.

The two signals are fused into a single ``combined_context`` string that can
be injected directly into an LLM prompt as grounding context.

Search modes
------------
``"local"``
    Entity-centric retrieval.  Matches the query against graph entities,
    traverses up to depth-2 neighbourhoods, collects source documents, and
    returns the resulting subgraph context.  Best for specific entity queries
    (e.g. "M-케어 건강보험 보장 내용").

``"global"``
    Community-summary retrieval.  Uses all available community summaries as
    the context block.  Best for broad, thematic questions that span many
    entities (e.g. "건강보험 상품군 전체 개요").

``"hybrid"`` (default)
    Runs vector search first, then augments the results with graph context
    derived from entity mentions in the query.  Combines both signals into a
    richer context block.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.graph.models import Community, Entity, Relationship
from backend.graph.store import GraphStore

logger = logging.getLogger(__name__)

# Maximum depth for graph traversal in local / hybrid modes
_TRAVERSAL_DEPTH = 2
# Minimum fuzzy-match score (0–100) for entity name matching against query
_ENTITY_MATCH_THRESHOLD = 60


@dataclass
class GraphRAGResult:
    """Structured result from a GraphRAG search.

    Attributes:
        query: The original search query.
        mode: Search mode used — ``"local"``, ``"global"``, or ``"hybrid"``.
        vector_results: Raw result dicts from ChromaDB (list of
            ``{id, document, metadata, distance, score}`` dicts).
        graph_context: Formatted string describing related entities,
            relationships, and community summaries for LLM injection.
        matched_entities: Entities whose names appeared in / matched the query.
        related_entities: Entities discovered via graph traversal from the
            matched entities.
        communities: Community records relevant to the matched entities.
        source_documents: Deduplicated list of vault-relative document paths
            referenced by the matched and related entities.
        combined_context: Full context block (vector + graph) ready for LLM
            consumption.
    """

    query: str
    mode: str
    vector_results: list[dict[str, Any]] = field(default_factory=list)
    graph_context: str = ""
    matched_entities: list[dict[str, Any]] = field(default_factory=list)
    related_entities: list[dict[str, Any]] = field(default_factory=list)
    communities: list[dict[str, Any]] = field(default_factory=list)
    source_documents: list[str] = field(default_factory=list)
    combined_context: str = ""


def _entity_to_dict(entity: Entity) -> dict[str, Any]:
    """Serialize an :class:`~backend.graph.models.Entity` to a plain dict.

    Args:
        entity: Entity to serialize.

    Returns:
        Dict representation suitable for JSON responses.
    """
    return {
        "id": entity.id,
        "name": entity.name,
        "type": entity.entity_type,
        "mentions": entity.mentions,
        "properties": entity.properties,
        "source_paths": entity.source_paths,
    }


def _community_to_dict(community: Community) -> dict[str, Any]:
    """Serialize a :class:`~backend.graph.models.Community` to a plain dict.

    Args:
        community: Community to serialize.

    Returns:
        Dict representation suitable for JSON responses.
    """
    return {
        "id": community.id,
        "name": community.name,
        "entity_ids": community.entity_ids,
        "summary": community.summary,
        "level": community.level,
    }


class GraphRAGEngine:
    """GraphRAG retrieval engine combining vector search and graph traversal.

    Args:
        graph_store: The :class:`~backend.graph.store.GraphStore` instance
            providing graph traversal capabilities.
        iam_engine: Optional :class:`~backend.core.iam.IAMEngine` instance for
            ACL filtering of source documents.  When ``None``, source document
            filtering is skipped.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        iam_engine: Any | None = None,
    ) -> None:
        self._store = graph_store
        self._iam = iam_engine

    # ------------------------------------------------------------------
    # Main search entry point
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        user_id: str,
        user_roles: list[str],
        mode: str = "hybrid",
        n_results: int = 10,
    ) -> GraphRAGResult:
        """Execute a GraphRAG search and return an enriched result.

        Args:
            query: Natural-language search query.
            user_id: Requesting user's identifier (for ACL filtering).
            user_roles: Roles assigned to the user (for ACL filtering).
            mode: One of ``"local"``, ``"global"``, or ``"hybrid"``.
            n_results: Maximum number of vector search results to fetch.

        Returns:
            A :class:`GraphRAGResult` containing all retrieval signals and
            the combined context string for LLM consumption.
        """
        mode = mode.lower()
        if mode == "local":
            return await self._search_local(query, user_id, user_roles, n_results)
        if mode == "global":
            return await self._search_global(query, user_id, user_roles, n_results)
        return await self._search_hybrid(query, user_id, user_roles, n_results)

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------

    async def _search_local(
        self,
        query: str,
        user_id: str,
        user_roles: list[str],
        n_results: int,
    ) -> GraphRAGResult:
        """Local mode: entity-centric graph traversal without vector search.

        Steps:
        1. Match query tokens against graph entity names.
        2. Traverse depth-2 neighbourhood of matched entities.
        3. Collect source documents from all entities (ACL filtered).
        4. Retrieve community summaries for matched entities.

        Args:
            query: Search query.
            user_id: Requesting user ID.
            user_roles: User role list.
            n_results: Unused in local mode; kept for interface consistency.

        Returns:
            :class:`GraphRAGResult` with graph-only context.
        """
        matched = self._match_entities(query)
        related_ents: list[Entity] = []
        all_rels: list[Relationship] = []

        for entity in matched:
            neighbors, rels = self._store.get_neighbors(
                entity.id, depth=_TRAVERSAL_DEPTH
            )
            related_ents.extend(neighbors)
            all_rels.extend(rels)

        # Deduplicate related entities
        seen_ids: set[str] = {e.id for e in matched}
        unique_related: list[Entity] = []
        for e in related_ents:
            if e.id not in seen_ids:
                seen_ids.add(e.id)
                unique_related.append(e)

        communities = self._get_entity_communities(matched)
        source_docs = self.get_related_documents(
            [e.id for e in matched + unique_related],
            user_id,
            user_roles,
        )

        graph_ctx = self.build_graph_context(
            entities=matched + unique_related,
            relationships=all_rels,
            communities=communities,
        )

        combined = self._build_combined_context(
            query=query,
            vector_text="",
            graph_context=graph_ctx,
        )

        return GraphRAGResult(
            query=query,
            mode="local",
            vector_results=[],
            graph_context=graph_ctx,
            matched_entities=[_entity_to_dict(e) for e in matched],
            related_entities=[_entity_to_dict(e) for e in unique_related],
            communities=[_community_to_dict(c) for c in communities],
            source_documents=source_docs,
            combined_context=combined,
        )

    async def _search_global(
        self,
        query: str,
        user_id: str,
        user_roles: list[str],
        n_results: int,
    ) -> GraphRAGResult:
        """Global mode: uses all community summaries as broad context.

        Best for high-level thematic queries that span many entities.

        Args:
            query: Search query.
            user_id: Requesting user ID.
            user_roles: User role list.
            n_results: Number of vector search results; also used to limit
                vector retrieval for supplementary document sources.

        Returns:
            :class:`GraphRAGResult` with community-summary-heavy context.
        """
        # Gather all communities with non-empty summaries first
        all_communities = [
            c for c in self._store.get_communities() if c.summary
        ]
        # Fall back to all communities if none have summaries yet
        if not all_communities:
            all_communities = self._store.get_communities()

        # Also run vector search to surface relevant document snippets
        vector_results = await asyncio.to_thread(
            self._run_vector_search, query, user_id, user_roles, n_results
        )

        community_ctx_parts = ["=== 커뮤니티 요약 ==="]
        for c in all_communities[:20]:  # cap at 20 to control context length
            community_ctx_parts.append(f"- {c.name}: {c.summary or '(요약 없음)'}")
        community_ctx = "\n".join(community_ctx_parts)

        combined = self._build_combined_context(
            query=query,
            vector_text=self._format_vector_results(vector_results),
            graph_context=community_ctx,
        )

        return GraphRAGResult(
            query=query,
            mode="global",
            vector_results=vector_results,
            graph_context=community_ctx,
            matched_entities=[],
            related_entities=[],
            communities=[_community_to_dict(c) for c in all_communities],
            source_documents=self._extract_source_paths_from_vector(vector_results),
            combined_context=combined,
        )

    async def _search_hybrid(
        self,
        query: str,
        user_id: str,
        user_roles: list[str],
        n_results: int,
    ) -> GraphRAGResult:
        """Hybrid mode: vector search + graph traversal fused together.

        Steps:
        1. Run vector search via ChromaDB (ACL-enforced).
        2. Match entity names from query against the knowledge graph.
        3. Traverse depth-2 neighbourhood of matched entities.
        4. Collect community summaries for matched entities.
        5. Merge all source documents (ACL filtered).
        6. Build combined context string.

        Args:
            query: Search query.
            user_id: Requesting user ID.
            user_roles: User role list.
            n_results: Number of vector search results to retrieve.

        Returns:
            :class:`GraphRAGResult` with full hybrid context.
        """
        # Step 1: Vector search (runs in thread pool to avoid blocking)
        vector_results = await asyncio.to_thread(
            self._run_vector_search, query, user_id, user_roles, n_results
        )

        # Step 2: Match entities from query
        matched = self._match_entities(query)

        # Step 3: Graph traversal
        related_ents: list[Entity] = []
        all_rels: list[Relationship] = []
        for entity in matched:
            neighbors, rels = self._store.get_neighbors(
                entity.id, depth=_TRAVERSAL_DEPTH
            )
            related_ents.extend(neighbors)
            all_rels.extend(rels)

        # Deduplicate related entities
        seen_ids: set[str] = {e.id for e in matched}
        unique_related: list[Entity] = []
        for e in related_ents:
            if e.id not in seen_ids:
                seen_ids.add(e.id)
                unique_related.append(e)

        # Step 4: Community summaries
        communities = self._get_entity_communities(matched)

        # Step 5: Merge source documents
        graph_doc_ids = [e.id for e in matched + unique_related]
        graph_docs = self.get_related_documents(graph_doc_ids, user_id, user_roles)
        vector_docs = self._extract_source_paths_from_vector(vector_results)
        source_docs = list(dict.fromkeys(vector_docs + graph_docs))

        # Step 6: Build context strings
        graph_ctx = self.build_graph_context(
            entities=matched + unique_related,
            relationships=all_rels,
            communities=communities,
        )
        vector_text = self._format_vector_results(vector_results)
        combined = self._build_combined_context(
            query=query,
            vector_text=vector_text,
            graph_context=graph_ctx,
        )

        return GraphRAGResult(
            query=query,
            mode="hybrid",
            vector_results=vector_results,
            graph_context=graph_ctx,
            matched_entities=[_entity_to_dict(e) for e in matched],
            related_entities=[_entity_to_dict(e) for e in unique_related],
            communities=[_community_to_dict(c) for c in communities],
            source_documents=source_docs,
            combined_context=combined,
        )

    # ------------------------------------------------------------------
    # Context building helpers
    # ------------------------------------------------------------------

    def build_graph_context(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        communities: list[Community],
    ) -> str:
        """Format graph data into a readable context string for LLM consumption.

        Output format example::

            === 관련 엔티티 ===
            - [상품] M-케어 건강보험: 주계약, 갱신형 건강보험 ...
            - [조직] 미래에셋생명: 보험사 ...

            === 관계 ===
            - M-케어 건강보험 --[보장]--> 암진단금
            - M-케어 건강보험 --[소속]--> 미래에셋생명

            === 커뮤니티 요약 ===
            - 건강보험 상품군: M-케어 시리즈는 갱신형 건강보험으로 ...

        Args:
            entities: Entities to include in the context block.
            relationships: Relationships to describe.
            communities: Community summaries to append.

        Returns:
            Formatted multi-line context string.  Returns an empty string
            when all three inputs are empty.
        """
        if not entities and not relationships and not communities:
            return ""

        parts: list[str] = []

        if entities:
            parts.append("=== 관련 엔티티 ===")
            for entity in entities:
                desc = entity.properties.get("description", "")
                desc_str = f": {desc}" if desc else ""
                parts.append(f"- [{entity.entity_type}] {entity.name}{desc_str}")

        if relationships:
            parts.append("\n=== 관계 ===")
            seen_rels: set[tuple[str, str, str]] = set()
            for rel in relationships:
                key = (rel.source_id, rel.target_id, rel.relation_type)
                if key in seen_rels:
                    continue
                seen_rels.add(key)
                # Try to resolve human-readable names
                src_entity = self._store.get_entity(rel.source_id)
                tgt_entity = self._store.get_entity(rel.target_id)
                src_name = src_entity.name if src_entity else rel.source_id
                tgt_name = tgt_entity.name if tgt_entity else rel.target_id
                parts.append(f"- {src_name} --[{rel.relation_type}]--> {tgt_name}")

        if communities:
            parts.append("\n=== 커뮤니티 요약 ===")
            for community in communities:
                summary = community.summary or "(요약 없음)"
                parts.append(f"- {community.name}: {summary}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Document retrieval helpers
    # ------------------------------------------------------------------

    def get_related_documents(
        self,
        entity_ids: list[str],
        user_id: str,
        user_roles: list[str],
    ) -> list[str]:
        """Collect source document paths from entities, filtered by ACL.

        Retrieves the ``source_paths`` field from each entity in *entity_ids*,
        deduplicates the paths, and then filters them against the user's read
        permissions via the IAM engine (if configured).

        Args:
            entity_ids: List of entity IDs whose source paths to gather.
            user_id: Requesting user's identifier.
            user_roles: User's role list (used only when IAM engine is absent
                for a permissive fallback).

        Returns:
            Deduplicated list of accessible vault-relative document paths.
        """
        seen: dict[str, None] = {}  # ordered set

        for entity_id in entity_ids:
            entity = self._store.get_entity(entity_id)
            if entity is None:
                continue
            for path in entity.source_paths:
                seen[path] = None

        all_paths = list(seen.keys())

        if self._iam is None:
            return all_paths

        # Filter by IAM read permissions
        return [p for p in all_paths if self._iam.can_read(user_id, p)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_entities(self, query: str) -> list[Entity]:
        """Find entities whose names appear as substrings in the query.

        Uses case-insensitive token and full-name substring matching against
        all entities in the graph store.  Results are deduplicated and sorted
        by mention count.

        Args:
            query: The search query to match entity names against.

        Returns:
            List of matched entities, sorted by mention count (descending).
        """
        query_lower = query.lower()
        # Extract alphanumeric / Korean tokens from the query
        query_tokens = set(re.findall(r"[a-zA-Z0-9가-힣\-]+", query_lower))

        matched: dict[str, Entity] = {}
        for entity in self._store.search_entities(query, limit=50):
            if entity.id not in matched:
                matched[entity.id] = entity

        # Also do a simple substring walk for shorter entity names
        for entity in self._store.search_entities("", limit=200):
            name_lower = entity.name.lower()
            if name_lower in query_lower:
                matched[entity.id] = entity
                continue
            # Match if any query token appears in the entity name
            name_tokens = set(re.findall(r"[a-zA-Z0-9가-힣\-]+", name_lower))
            if query_tokens & name_tokens:
                matched[entity.id] = entity

        result = list(matched.values())
        result.sort(key=lambda e: e.mentions, reverse=True)
        return result[:20]  # cap to avoid combinatorial explosion

    def _get_entity_communities(self, entities: list[Entity]) -> list[Community]:
        """Return deduplicated communities containing any entity in *entities*.

        Args:
            entities: Entities to look up community membership for.

        Returns:
            Deduplicated list of relevant communities.
        """
        all_communities = self._store.get_communities()
        entity_ids = {e.id for e in entities}
        seen_ids: set[str] = set()
        result: list[Community] = []

        for community in all_communities:
            if community.id in seen_ids:
                continue
            if entity_ids & set(community.entity_ids):
                seen_ids.add(community.id)
                result.append(community)

        return result

    def _run_vector_search(
        self,
        query: str,
        user_id: str,
        user_roles: list[str],
        n_results: int,
    ) -> list[dict[str, Any]]:
        """Execute a hybrid vector+keyword search (synchronous, for thread pool).

        Falls back to an empty list when the vector store is unavailable or
        has no documents indexed, so that graph-only results are still returned.

        Args:
            query: Search query.
            user_id: Requesting user ID.
            user_roles: User role list.
            n_results: Maximum number of results.

        Returns:
            List of result dicts from :func:`~backend.indexer.search.hybrid_search`.
        """
        try:
            from backend.indexer.search import hybrid_search  # noqa: PLC0415
            from backend.core.iam import IAMEngine  # noqa: PLC0415

            iam = self._iam
            if iam is None:
                # Instantiate a read-only IAM engine from the default path
                from backend.config import settings as _settings  # noqa: PLC0415

                iam = IAMEngine(_settings.vault_root / "iam.yaml")

            return hybrid_search(
                query=query,
                user_id=user_id,
                iam=iam,
                n_results=n_results,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("GraphRAGEngine: vector search failed (non-fatal): %s", exc)
            return []

    @staticmethod
    def _format_vector_results(results: list[dict[str, Any]]) -> str:
        """Format vector search results as a numbered passage list.

        Args:
            results: List of result dicts from the vector search.

        Returns:
            Formatted multi-line string, or empty string when *results* is empty.
        """
        if not results:
            return ""
        lines = ["=== 검색 결과 (벡터 검색) ==="]
        for i, r in enumerate(results, 1):
            doc = r.get("document", "")
            meta = r.get("metadata") or {}
            source = meta.get("source_path", "")
            score = r.get("score", 0.0)
            heading = meta.get("heading", "")
            header = f"[{i}] {source}"
            if heading:
                header += f" > {heading}"
            header += f" (score={score:.3f})"
            lines.append(header)
            # Include up to 500 chars of the chunk
            lines.append(doc[:500].strip())
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _extract_source_paths_from_vector(results: list[dict[str, Any]]) -> list[str]:
        """Extract unique ``source_path`` values from vector search results.

        Args:
            results: List of result dicts.

        Returns:
            Deduplicated list of vault-relative document paths.
        """
        seen: dict[str, None] = {}
        for r in results:
            meta = r.get("metadata") or {}
            path = meta.get("source_path", "")
            if path:
                seen[path] = None
        return list(seen.keys())

    @staticmethod
    def _build_combined_context(
        query: str,
        vector_text: str,
        graph_context: str,
    ) -> str:
        """Merge vector results and graph context into a single LLM context block.

        Args:
            query: Original query (used as a section header for clarity).
            vector_text: Formatted vector search output string.
            graph_context: Formatted graph context string.

        Returns:
            Combined context string.
        """
        parts: list[str] = [f"[검색 쿼리: {query}]", ""]
        if vector_text:
            parts.append(vector_text)
            parts.append("")
        if graph_context:
            parts.append(graph_context)
        return "\n".join(parts).strip()
