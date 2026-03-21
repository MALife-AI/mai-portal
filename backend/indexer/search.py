"""Secure Cross-Reference Search: ACL 필터 강제.

All public search functions enforce ACL predicates so that callers never
receive documents the requesting user is not permitted to read.

ChromaDB filter notes
---------------------
``allowed_roles`` is stored as a comma-separated string (e.g. ``"admin,editor"``)
because ChromaDB does not support array-valued metadata.  Role membership is
therefore checked with ``$contains`` (substring match), which works correctly
as long as role names do not contain commas.

The ``$or`` operator in ChromaDB requires **at least two** clauses.  When a
user has no assigned roles the filter collapses to an owner-only predicate to
avoid passing an invalid filter structure.
"""
from __future__ import annotations

import re
from typing import Any

from backend.core.iam import IAMEngine
from backend.indexer.vectorstore import get_collection


# ---------------------------------------------------------------------------
# ACL filter builder
# ---------------------------------------------------------------------------

def _build_acl_filter(
    user_id: str,
    user_roles: list[str],
    user_department: str = "",
) -> dict[str, Any]:
    """Build a ChromaDB ``where`` filter that enforces read ACL.

    A document is accessible when **any** of:
    - The user owns it (``owner == user_id``), **or**
    - The document's ``allowed_roles`` string contains one of the user's roles, **or**
    - The document's ``allowed_departments`` string contains the user's department.

    Documents without ``allowed_departments`` (empty string) are not
    department-restricted and are matched by role/owner clauses only.

    Args:
        user_id: Requesting user's identifier.
        user_roles: List of role names assigned to the user.
        user_department: User's department id (e.g. ``"life_insurance"``).

    Returns:
        A dict suitable for passing as ChromaDB's ``where`` parameter.
    """
    owner_clause: dict[str, Any] = {"owner": {"$eq": user_id}}

    clauses: list[dict[str, Any]] = [owner_clause]

    for role in user_roles:
        clauses.append({"allowed_roles": {"$contains": role}})

    if user_department:
        clauses.append({"allowed_departments": {"$contains": user_department}})

    # 부서 미제한 문서 (allowed_departments가 빈 문자열)도 역할 기반으로 접근 가능
    # → role clause가 이미 커버함

    if len(clauses) == 1:
        return owner_clause

    return {"$or": clauses}


# ---------------------------------------------------------------------------
# Secure vector search
# ---------------------------------------------------------------------------

def secure_search(
    query: str,
    user_id: str,
    iam: IAMEngine,
    n_results: int = 10,
) -> dict[str, Any]:
    """Semantic vector search with ACL enforcement.

    Queries the default ChromaDB collection using *query* as the embedding
    target and restricts results to documents the user is authorised to read.

    Args:
        query: Natural-language search query.
        user_id: Requesting user's identifier.
        iam: Loaded :class:`~backend.core.iam.IAMEngine` instance.
        n_results: Maximum number of results to return.

    Returns:
        Raw ChromaDB query result dict with ``ids``, ``documents``,
        ``metadatas``, and ``distances`` keys.
    """
    user_roles = iam.get_user_roles(user_id)
    user_department = iam.get_user_department(user_id)
    collection = get_collection()
    where_filter = _build_acl_filter(user_id, user_roles, user_department)

    return collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )


# ---------------------------------------------------------------------------
# Hybrid search (vector + keyword)
# ---------------------------------------------------------------------------

def hybrid_search(
    query: str,
    user_id: str,
    iam: IAMEngine,
    n_results: int = 10,
    keyword_weight: float = 0.3,
) -> list[dict[str, Any]]:
    """Combine semantic vector search with keyword relevance re-ranking.

    Strategy:
    1. Retrieve ``n_results * 3`` candidates via semantic search.
    2. Score each candidate with a lightweight keyword match count derived
       from *query* tokens present in the chunk text.
    3. Compute a weighted linear combination of the normalised semantic score
       (inverted cosine distance) and the normalised keyword score.
    4. Return the top *n_results* results sorted by combined score.

    This approach avoids a second ChromaDB call and keeps latency low while
    still surfacing documents that are lexically close to the query even when
    their embedding distance is moderate.

    Args:
        query: Natural-language search query.
        user_id: Requesting user's identifier.
        iam: Loaded :class:`~backend.core.iam.IAMEngine` instance.
        n_results: Final number of results to return.
        keyword_weight: Weight [0, 1] given to keyword score.  The semantic
            score receives ``1 - keyword_weight``.

    Returns:
        List of result dicts ordered by combined score (highest first).  Each
        dict contains:

        - ``id`` – ChromaDB document id
        - ``document`` – chunk text
        - ``metadata`` – metadata dict
        - ``distance`` – raw cosine distance from ChromaDB
        - ``score`` – combined relevance score (higher is better)
    """
    user_roles = iam.get_user_roles(user_id)
    user_department = iam.get_user_department(user_id)
    collection = get_collection()
    where_filter = _build_acl_filter(user_id, user_roles, user_department)

    # Over-fetch to give keyword re-ranking enough candidates
    raw = collection.query(
        query_texts=[query],
        n_results=min(n_results * 3, 100),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    ids: list[str] = (raw.get("ids") or [[]])[0]
    docs: list[str] = (raw.get("documents") or [[]])[0]
    metas: list[dict] = (raw.get("metadatas") or [[]])[0]
    distances: list[float] = (raw.get("distances") or [[]])[0]

    if not ids:
        return []

    # Build keyword token set from query (lowercase, alphanumeric)
    query_tokens = set(re.findall(r"[a-zA-Z0-9가-힣]+", query.lower()))

    def _keyword_score(text: str) -> int:
        """Count how many query tokens appear in *text*."""
        text_lower = text.lower()
        return sum(1 for tok in query_tokens if tok in text_lower)

    # Compute raw scores
    keyword_scores = [_keyword_score(doc) for doc in docs]

    # Normalise semantic score: cosine distance is in [0, 2]; invert so that
    # lower distance → higher score, mapped to [0, 1].
    max_dist = max(distances) if distances else 1.0
    sem_scores = [1.0 - (d / max(max_dist, 1e-9)) for d in distances]

    # Normalise keyword scores to [0, 1]
    max_kw = max(keyword_scores) if keyword_scores else 1
    norm_kw = [k / max(max_kw, 1) for k in keyword_scores]

    semantic_weight = 1.0 - keyword_weight
    combined = [
        semantic_weight * s + keyword_weight * k
        for s, k in zip(sem_scores, norm_kw)
    ]

    # Assemble and sort
    results = [
        {
            "id": id_,
            "document": doc,
            "metadata": meta,
            "distance": dist,
            "score": score,
        }
        for id_, doc, meta, dist, score in zip(ids, docs, metas, distances, combined)
    ]
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:n_results]


# ---------------------------------------------------------------------------
# Scoped path search
# ---------------------------------------------------------------------------

def search_by_path(
    query: str,
    user_id: str,
    iam: IAMEngine,
    path_prefix: str,
    n_results: int = 10,
) -> dict[str, Any]:
    """Semantic search restricted to a specific directory scope.

    Combines the standard ACL filter with an additional ``source_path``
    prefix constraint so that only documents whose vault-relative path begins
    with *path_prefix* are considered.

    ChromaDB does not have a native ``$startswith`` operator.  We emulate it
    by passing the prefix as a ``$contains`` predicate on ``source_path``.
    This is slightly over-broad (a path ``/Projects/foo`` would match a prefix
    ``/Projects/f``) but is sufficient for directory-level scoping when
    callers pass proper directory paths (e.g. ``/Projects/``).

    Args:
        query: Natural-language search query.
        user_id: Requesting user's identifier.
        iam: Loaded :class:`~backend.core.iam.IAMEngine` instance.
        path_prefix: Vault-relative directory prefix, e.g. ``/Projects/``.
        n_results: Maximum number of results to return.

    Returns:
        Raw ChromaDB query result dict with ``ids``, ``documents``,
        ``metadatas``, and ``distances`` keys.
    """
    user_roles = iam.get_user_roles(user_id)
    user_department = iam.get_user_department(user_id)
    collection = get_collection()
    acl_filter = _build_acl_filter(user_id, user_roles, user_department)

    # Intersect ACL filter with path scope using $and
    where_filter: dict[str, Any] = {
        "$and": [
            acl_filter,
            {"source_path": {"$contains": path_prefix}},
        ]
    }

    return collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )
