from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    """그래프 노드: 문서에서 추출된 엔티티.

    Attributes:
        id: Unique identifier derived from slugified entity name.
        name: Human-readable display name (e.g. "M-케어 건강보험").
        entity_type: Category - person, product, regulation, organization,
            concept, document, or term.
        properties: Arbitrary metadata attached to the entity.
        source_paths: Relative vault paths of documents that mention this entity.
        mentions: Running count of how many times this entity has been seen.
    """

    id: str
    name: str
    entity_type: str  # person | product | regulation | organization | concept | document | term
    properties: dict[str, Any] = field(default_factory=dict)
    source_paths: list[str] = field(default_factory=list)
    mentions: int = 0


@dataclass
class Relationship:
    """그래프 엣지: 엔티티 간 관계.

    Attributes:
        source_id: ID of the source Entity node.
        target_id: ID of the target Entity node.
        relation_type: Semantic label - covers, depends_on, regulates,
            belongs_to, references, etc.
        properties: Arbitrary metadata for the edge.
        source_path: Vault-relative path of the document that established
            this relationship.
        weight: Accumulated strength of the relationship (incremented on
            repeated observation).
    """

    source_id: str
    target_id: str
    relation_type: str  # covers | depends_on | regulates | belongs_to | references | ...
    properties: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""
    weight: float = 1.0


@dataclass
class Community:
    """그래프 커뮤니티: 밀접 연결된 엔티티 그룹.

    Attributes:
        id: Unique community identifier.
        name: Human-readable label, typically derived from dominant entities.
        entity_ids: Sorted list of Entity IDs that belong to this community.
        summary: LLM-generated natural-language description of the cluster.
        level: Hierarchy level (0 = leaf, higher = broader aggregation).
    """

    id: str
    name: str
    entity_ids: list[str] = field(default_factory=list)
    summary: str = ""
    level: int = 0
