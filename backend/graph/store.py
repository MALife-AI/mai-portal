"""Knowledge Graph Store: NetworkX + JSON 영속화."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx
from rapidfuzz import fuzz, process

from backend.config import settings
from backend.graph.models import Community, Entity, Relationship

logger = logging.getLogger(__name__)

_DEFAULT_PERSIST_PATH: Path = settings.vault_root / ".graph" / "knowledge_graph.json"


class GraphStore:
    """NetworkX DiGraph-backed knowledge graph with JSON persistence.

    The graph uses node/edge attribute dicts that mirror the Entity and
    Relationship dataclass fields so that (de)serialisation is transparent
    via ``networkx.node_link_data`` / ``networkx.node_link_graph``.

    Args:
        persist_path: File path for JSON snapshot.  Defaults to
            ``<vault_root>/.graph/knowledge_graph.json``.
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        self._path: Path = persist_path or _DEFAULT_PERSIST_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._graph: nx.DiGraph = nx.DiGraph()
        if self._path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        """Add or update a node in the graph.

        If the node already exists the ``mentions`` counter is incremented
        and ``source_paths`` is extended with any new paths from *entity*.

        Args:
            entity: Entity dataclass instance to upsert.
        """
        if self._graph.has_node(entity.id):
            existing = self._graph.nodes[entity.id]
            existing["mentions"] = existing.get("mentions", 0) + 1
            known_paths: list[str] = existing.get("source_paths", [])
            for path in entity.source_paths:
                if path not in known_paths:
                    known_paths.append(path)
            existing["source_paths"] = known_paths
            # Merge properties without overwriting existing keys
            props: dict[str, Any] = existing.get("properties", {})
            props.update({k: v for k, v in entity.properties.items() if k not in props})
            existing["properties"] = props
        else:
            self._graph.add_node(
                entity.id,
                name=entity.name,
                entity_type=entity.entity_type,
                properties=entity.properties,
                source_paths=list(entity.source_paths),
                mentions=entity.mentions if entity.mentions > 0 else 1,
            )

    def add_relationship(self, rel: Relationship) -> None:
        """Add or update a directed edge in the graph.

        Both endpoint nodes are auto-created as stub ``concept`` entities if
        they do not yet exist so the graph stays consistent.  If the edge
        already exists its ``weight`` is incremented by 1.

        Args:
            rel: Relationship dataclass instance to upsert.
        """
        # Ensure nodes exist
        for node_id in (rel.source_id, rel.target_id):
            if not self._graph.has_node(node_id):
                self._graph.add_node(
                    node_id,
                    name=node_id,
                    entity_type="concept",
                    properties={},
                    source_paths=[],
                    mentions=0,
                )

        if self._graph.has_edge(rel.source_id, rel.target_id):
            edge_data = self._graph.edges[rel.source_id, rel.target_id]
            edge_data["weight"] = edge_data.get("weight", 1.0) + 1.0
        else:
            self._graph.add_edge(
                rel.source_id,
                rel.target_id,
                relation_type=rel.relation_type,
                properties=rel.properties,
                source_path=rel.source_path,
                weight=rel.weight,
            )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_entity(self, entity_id: str) -> Entity | None:
        """Return the Entity for *entity_id*, or ``None`` if absent.

        Args:
            entity_id: Node ID to look up.

        Returns:
            Reconstructed :class:`Entity` or ``None``.
        """
        if not self._graph.has_node(entity_id):
            return None
        return self._node_to_entity(entity_id, self._graph.nodes[entity_id])

    def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> tuple[list[Entity], list[Relationship]]:
        """BFS traversal from *entity_id* up to *depth* hops.

        Both outgoing and incoming edges are traversed so the neighbourhood
        is undirected in practice, which is more useful for knowledge graph
        exploration.

        Args:
            entity_id: Starting node.
            depth: Maximum number of hops from the start node.
            relation_types: If provided, only traverse edges whose
                ``relation_type`` is in this list.

        Returns:
            Tuple of (entities, relationships) collected during traversal.
            The start node itself is not included in the entity list.
        """
        if not self._graph.has_node(entity_id):
            return [], []

        visited_nodes: set[str] = {entity_id}
        visited_edges: set[tuple[str, str]] = set()
        frontier: list[str] = [entity_id]
        entities: list[Entity] = []
        relationships: list[Relationship] = []

        for _ in range(depth):
            next_frontier: list[str] = []
            for node in frontier:
                # Outgoing edges
                for _, target, data in self._graph.out_edges(node, data=True):
                    rtype: str = data.get("relation_type", "")
                    if relation_types and rtype not in relation_types:
                        continue
                    edge_key = (node, target)
                    if edge_key not in visited_edges:
                        visited_edges.add(edge_key)
                        relationships.append(self._edge_to_relationship(node, target, data))
                    if target not in visited_nodes:
                        visited_nodes.add(target)
                        entities.append(self._node_to_entity(target, self._graph.nodes[target]))
                        next_frontier.append(target)
                # Incoming edges
                for source, _, data in self._graph.in_edges(node, data=True):
                    rtype = data.get("relation_type", "")
                    if relation_types and rtype not in relation_types:
                        continue
                    edge_key = (source, node)
                    if edge_key not in visited_edges:
                        visited_edges.add(edge_key)
                        relationships.append(self._edge_to_relationship(source, node, data))
                    if source not in visited_nodes:
                        visited_nodes.add(source)
                        entities.append(self._node_to_entity(source, self._graph.nodes[source]))
                        next_frontier.append(source)
            frontier = next_frontier

        return entities, relationships

    def get_subgraph(
        self,
        entity_ids: list[str],
        include_neighbors: bool = True,
    ) -> dict[str, Any]:
        """Return a serialisable subgraph dict for frontend visualisation.

        Args:
            entity_ids: Seed node IDs to include.
            include_neighbors: When ``True``, all direct (depth-1) neighbours
                of the seed nodes are also included.

        Returns:
            Dict with keys ``nodes`` and ``edges``.
        """
        node_set: set[str] = set(entity_ids)

        if include_neighbors:
            for eid in list(entity_ids):
                if self._graph.has_node(eid):
                    node_set.update(self._graph.successors(eid))
                    node_set.update(self._graph.predecessors(eid))

        # Keep only nodes that exist
        node_set = {n for n in node_set if self._graph.has_node(n)}
        sub = self._graph.subgraph(node_set)

        nodes = [
            {
                "id": n,
                **{k: v for k, v in sub.nodes[n].items()},
            }
            for n in sub.nodes
        ]
        edges = [
            {
                "source": u,
                "target": v,
                **{k: val for k, val in data.items()},
            }
            for u, v, data in sub.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[Entity]:
        """Fuzzy name search over all entities using rapidfuzz.

        Args:
            query: Search string.
            entity_type: Optional filter to a specific entity category.
            limit: Maximum number of results to return.

        Returns:
            List of :class:`Entity` objects ranked by fuzzy match score.
        """
        candidates: list[tuple[str, str]] = []  # (node_id, name)
        for node_id, data in self._graph.nodes(data=True):
            if entity_type and data.get("entity_type") != entity_type:
                continue
            candidates.append((node_id, data.get("name", node_id)))

        if not candidates:
            return []

        names = [c[1] for c in candidates]
        matches = process.extract(
            query,
            names,
            scorer=fuzz.WRatio,
            limit=limit,
        )

        results: list[Entity] = []
        for match_name, _score, idx in matches:
            node_id = candidates[idx][0]
            entity = self.get_entity(node_id)
            if entity is not None:
                results.append(entity)

        return results

    def get_communities(self, resolution: float = 1.0) -> list[Community]:
        """Detect communities using the Louvain algorithm.

        The directed graph is converted to undirected for community detection
        since Louvain operates on undirected graphs.

        Args:
            resolution: Louvain resolution parameter.  Higher values produce
                more, smaller communities.

        Returns:
            List of :class:`Community` objects, sorted by descending size.
        """
        if self._graph.number_of_nodes() == 0:
            return []

        undirected = self._graph.to_undirected()
        try:
            raw_communities: list[set[str]] = list(
                nx.community.louvain_communities(undirected, resolution=resolution, seed=42)
            )
        except Exception as exc:
            logger.warning("Community detection failed: %s", exc)
            return []

        communities: list[Community] = []
        for idx, node_set in enumerate(
            sorted(raw_communities, key=len, reverse=True)
        ):
            sorted_ids = sorted(node_set)
            # Derive a name from the highest-mention node in the community
            top_id = max(
                sorted_ids,
                key=lambda nid: self._graph.nodes[nid].get("mentions", 0),
            )
            top_name: str = self._graph.nodes[top_id].get("name", top_id)
            communities.append(
                Community(
                    id=f"community_{idx}",
                    name=f"{top_name} cluster",
                    entity_ids=sorted_ids,
                    summary="",
                    level=0,
                )
            )

        return communities

    def get_entity_by_source(self, source_path: str) -> list[Entity]:
        """Return all entities that cite *source_path* in their source_paths.

        Args:
            source_path: Vault-relative document path.

        Returns:
            List of matching :class:`Entity` objects.
        """
        results: list[Entity] = []
        for node_id, data in self._graph.nodes(data=True):
            if source_path in data.get("source_paths", []):
                results.append(self._node_to_entity(node_id, data))
        return results

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics about the graph.

        Returns:
            Dict with keys: ``node_count``, ``edge_count``,
            ``entity_types`` (type -> count), ``relation_types`` (type -> count),
            ``communities`` (count).
        """
        entity_types: dict[str, int] = {}
        for _, data in self._graph.nodes(data=True):
            etype: str = data.get("entity_type", "unknown")
            entity_types[etype] = entity_types.get(etype, 0) + 1

        relation_types: dict[str, int] = {}
        for _, _, data in self._graph.edges(data=True):
            rtype: str = data.get("relation_type", "unknown")
            relation_types[rtype] = relation_types.get(rtype, 0) + 1

        community_count = len(self.get_communities())

        return {
            "node_count": self._graph.number_of_nodes(),
            "edge_count": self._graph.number_of_edges(),
            "entity_types": entity_types,
            "relation_types": relation_types,
            "communities": community_count,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist the graph to JSON using ``nx.node_link_data`` format."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._graph)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        logger.info("Graph saved to %s (%d nodes, %d edges)",
                    self._path,
                    self._graph.number_of_nodes(),
                    self._graph.number_of_edges())

    def _load(self) -> None:
        """Restore the graph from the JSON snapshot at ``self._path``."""
        try:
            with self._path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            self._graph = nx.node_link_graph(data, directed=True, multigraph=False)
            logger.info(
                "Graph loaded from %s (%d nodes, %d edges)",
                self._path,
                self._graph.number_of_nodes(),
                self._graph.number_of_edges(),
            )
        except Exception as exc:
            logger.error("Failed to load graph from %s: %s – starting fresh", self._path, exc)
            self._graph = nx.DiGraph()

    def clear(self) -> None:
        """Reset the graph to an empty state (does not delete the JSON file)."""
        self._graph = nx.DiGraph()
        logger.info("Graph cleared")

    # ------------------------------------------------------------------
    # Visualisation export
    # ------------------------------------------------------------------

    def to_visualization_data(self) -> dict[str, Any]:
        """Return a lightweight frontend-ready representation of the graph.

        Properties and source_paths are omitted to keep the payload small.
        Use the entity detail API for full property access.
        """
        nodes = [
            {
                "id": node_id,
                "name": data.get("name", node_id),
                "type": data.get("entity_type", "concept"),
                "mentions": data.get("mentions", 0),
                "source_paths": data.get("source_paths", []),
            }
            for node_id, data in self._graph.nodes(data=True)
        ]

        edges = [
            {
                "source": u,
                "target": v,
                "type": data.get("relation_type", ""),
                "weight": data.get("weight", 1.0),
            }
            for u, v, data in self._graph.edges(data=True)
        ]

        communities = [
            {
                "id": c.id,
                "name": c.name,
                "entity_ids": c.entity_ids,
                "summary": c.summary,
                "level": c.level,
            }
            for c in self.get_communities()
        ]

        return {"nodes": nodes, "edges": edges, "communities": communities}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _node_to_entity(node_id: str, data: dict[str, Any]) -> Entity:
        return Entity(
            id=node_id,
            name=data.get("name", node_id),
            entity_type=data.get("entity_type", "concept"),
            properties=data.get("properties", {}),
            source_paths=data.get("source_paths", []),
            mentions=data.get("mentions", 0),
        )

    @staticmethod
    def _edge_to_relationship(source: str, target: str, data: dict[str, Any]) -> Relationship:
        return Relationship(
            source_id=source,
            target_id=target,
            relation_type=data.get("relation_type", ""),
            properties=data.get("properties", {}),
            source_path=data.get("source_path", ""),
            weight=data.get("weight", 1.0),
        )
