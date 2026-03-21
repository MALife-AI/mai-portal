"""ChromaDB Vector Store with ACL Metadata.

Provides:
- Persistent ChromaDB client and collection helpers.
- Full document indexing pipeline with frontmatter-derived ACL metadata.
- Upsert (delete-then-insert) semantics for re-indexing.
- Bulk vault reindexing.
"""
from __future__ import annotations

import asyncio
import logging
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.config import settings
from backend.core.frontmatter import parse_frontmatter
from backend.indexer.chunker import chunk_markdown

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None

# ---------------------------------------------------------------------------
# Client / collection helpers
# ---------------------------------------------------------------------------


def get_chroma_client() -> chromadb.ClientAPI:
    """Return (and lazily initialise) the singleton ChromaDB persistent client.

    Returns:
        A :class:`chromadb.ClientAPI` connected to the configured persist dir.
    """
    global _client
    if _client is None:
        settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection(name: str = "vault_docs") -> chromadb.Collection:
    """Get or create a named ChromaDB collection using cosine similarity.

    Args:
        name: Collection name.  Defaults to ``vault_docs``.

    Returns:
        The :class:`chromadb.Collection` instance.
    """
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# ACL helpers
# ---------------------------------------------------------------------------

def _derive_allowed_roles(rel_path: str, iam_path: Path) -> list[str]:
    """Determine which roles have read access to *rel_path* via iam.yaml."""
    if not iam_path.exists():
        return []

    import yaml

    with open(iam_path, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}

    matched: list[str] = []
    for role_name, policy in data.get("roles", {}).items():
        read_patterns: list[str] = (
            policy.get("allowed_paths", {}).get("read", [])
        )
        if any(fnmatch(rel_path, pat) for pat in read_patterns):
            matched.append(role_name)

    return sorted(matched)


def _derive_allowed_departments(rel_path: str, iam_path: Path) -> list[str]:
    """Shared/{dept_id}/ 경로에서 부서 ID를 추출하여 반환."""
    if not iam_path.exists():
        return []

    import yaml

    with open(iam_path, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}

    departments = data.get("departments", {})
    parts = rel_path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "Shared" and parts[1] in departments:
        return [parts[1]]
    return []


# ---------------------------------------------------------------------------
# Core indexing pipeline
# ---------------------------------------------------------------------------

async def index_document(
    rel_path: str,
    content: str,
    vault_root: Path,
    iam_path: Path,
) -> int:
    """Index a single document into ChromaDB with ACL metadata.

    Processing steps:

    1. Parse YAML frontmatter to extract ``owner``, ``allowed_roles``,
       and ``tags``.
    2. If ``allowed_roles`` is absent from frontmatter, derive the set of
       roles that have read access to *rel_path* from ``iam.yaml``.
    3. Chunk the document body with :func:`~backend.indexer.chunker.chunk_markdown`.
    4. Delete any pre-existing chunks for *rel_path* (upsert semantics).
    5. Insert each chunk with metadata fields required by the ACL search
       filter.

    ChromaDB metadata contract:
    - ``owner`` – string user-id
    - ``allowed_roles`` – comma-separated role string (e.g. ``"admin,editor"``)
      so that ChromaDB's ``$contains`` operator works on a single field.
    - ``source_path`` – *rel_path* value
    - ``heading`` – nearest ancestor heading for the chunk
    - ``tags`` – comma-separated tag string

    Args:
        rel_path: Vault-relative document path (used as a stable key).
        content: Full raw document text (may include frontmatter).
        vault_root: Absolute path to the vault root (reserved for future use,
            e.g. resolving ``[[wikilinks]]``).
        iam_path: Absolute path to ``iam.yaml``.

    Returns:
        Number of chunks written to ChromaDB.
    """
    # Step 1 – parse frontmatter
    meta, _body = parse_frontmatter(content)
    owner: str = str(meta.get("owner", ""))
    raw_roles: Any = meta.get("allowed_roles")
    raw_tags: Any = meta.get("tags", [])

    # Normalise allowed_roles to a list[str]
    if raw_roles is not None:
        if isinstance(raw_roles, list):
            allowed_roles: list[str] = [str(r) for r in raw_roles]
        else:
            allowed_roles = [s.strip() for s in str(raw_roles).split(",") if s.strip()]
    else:
        # Step 2 – derive from iam.yaml when not declared in frontmatter
        allowed_roles = await asyncio.to_thread( _derive_allowed_roles, rel_path, iam_path
        )

    # Derive allowed_departments from folder structure
    raw_depts: Any = meta.get("allowed_departments")
    if raw_depts is not None:
        if isinstance(raw_depts, list):
            allowed_departments: list[str] = [str(d) for d in raw_depts]
        else:
            allowed_departments = [s.strip() for s in str(raw_depts).split(",") if s.strip()]
    else:
        allowed_departments = await asyncio.to_thread(
            _derive_allowed_departments, rel_path, iam_path
        )

    # Normalise tags to a list[str]
    if isinstance(raw_tags, list):
        tags: list[str] = [str(t) for t in raw_tags]
    else:
        tags = [s.strip() for s in str(raw_tags).split(",") if s.strip()]

    # Step 3 – chunk the document
    chunks = chunk_markdown(content)
    if not chunks:
        logger.warning("index_document: no chunks produced for %s", rel_path)
        return 0

    collection = get_collection()

    # Step 4 – delete stale chunks for this path (upsert semantics)
    await asyncio.to_thread(_delete_chunks_for_path, collection, rel_path)

    # Step 5 – insert new chunks
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    roles_str = ",".join(allowed_roles)
    depts_str = ",".join(allowed_departments)
    tags_str = ",".join(tags)

    for i, chunk in enumerate(chunks):
        chunk_id = f"{rel_path}::chunk_{i}"
        ids.append(chunk_id)
        documents.append(chunk.content)
        metadatas.append({
            "owner": owner,
            "allowed_roles": roles_str,
            "allowed_departments": depts_str,
            "source_path": rel_path,
            "heading": chunk.heading,
            "tags": tags_str,
        })

    await asyncio.to_thread(
        lambda: collection.add(ids=ids, documents=documents, metadatas=metadatas),
    )

    logger.info("index_document: indexed %d chunks for %s", len(ids), rel_path)
    return len(ids)


# ---------------------------------------------------------------------------
# Deletion helpers
# ---------------------------------------------------------------------------

def _delete_chunks_for_path(
    collection: chromadb.Collection,
    rel_path: str,
) -> None:
    """Delete all chunks whose ``source_path`` matches *rel_path*.

    This is a synchronous helper suitable for running inside an executor.

    Args:
        collection: The target ChromaDB collection.
        rel_path: Vault-relative path to match against ``source_path``
            metadata.
    """
    existing = collection.get(
        where={"source_path": rel_path},
        include=[],
    )
    ids_to_delete: list[str] = existing.get("ids", [])
    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        logger.debug(
            "_delete_chunks_for_path: removed %d chunks for %s",
            len(ids_to_delete),
            rel_path,
        )


async def delete_document_index(rel_path: str) -> int:
    """Remove all indexed chunks for a document from ChromaDB.

    Args:
        rel_path: Vault-relative path identifying the document.

    Returns:
        Number of chunk records deleted.
    """
    collection = get_collection()
    existing = await asyncio.to_thread(
        lambda: collection.get(where={"source_path": rel_path}, include=[]),
    )
    ids_to_delete: list[str] = existing.get("ids", [])
    if not ids_to_delete:
        logger.info("delete_document_index: no chunks found for %s", rel_path)
        return 0

    await asyncio.to_thread(
        lambda: collection.delete(ids=ids_to_delete),
    )
    logger.info(
        "delete_document_index: deleted %d chunks for %s",
        len(ids_to_delete),
        rel_path,
    )
    return len(ids_to_delete)


# ---------------------------------------------------------------------------
# Bulk reindex
# ---------------------------------------------------------------------------

async def reindex_vault(vault_root: Path, iam_path: Path) -> dict[str, Any]:
    """Re-index every ``.md`` file in the vault from scratch.

    Walks *vault_root* recursively and calls :func:`index_document` for each
    Markdown file.  Errors on individual files are caught and reported in the
    returned summary so that a single corrupt file does not abort the entire
    run.

    Args:
        vault_root: Absolute path to the vault root directory.
        iam_path: Absolute path to ``iam.yaml``.

    Returns:
        Summary dict with keys:

        - ``indexed`` – number of files successfully indexed.
        - ``chunks`` – total chunks written.
        - ``errors`` – list of ``{path, error}`` dicts for failed files.
        - ``skipped`` – number of files that produced zero chunks.
    """
    md_files = list(vault_root.rglob("*.md"))
    logger.info("reindex_vault: found %d markdown files under %s", len(md_files), vault_root)

    indexed = 0
    total_chunks = 0
    errors: list[dict[str, str]] = []
    skipped = 0
    sem = asyncio.Semaphore(8)

    async def _index_one(md_file: Path) -> tuple[int, str | None]:
        rel_path = "/" + md_file.relative_to(vault_root).as_posix()
        async with sem:
            try:
                raw_content = await asyncio.to_thread(md_file.read_text, "utf-8")
                n = await index_document(
                    rel_path=rel_path,
                    content=raw_content,
                    vault_root=vault_root,
                    iam_path=iam_path,
                )
                return n, None
            except Exception as exc:  # noqa: BLE001
                logger.error("reindex_vault: failed to index %s: %s", rel_path, exc)
                return -1, str(exc)

    results = await asyncio.gather(*[_index_one(f) for f in md_files])
    for md_file, (n, err) in zip(md_files, results):
        rel_path = "/" + md_file.relative_to(vault_root).as_posix()
        if err is not None:
            errors.append({"path": rel_path, "error": err})
        elif n == 0:
            skipped += 1
        else:
            indexed += 1
            total_chunks += n

    summary: dict[str, Any] = {
        "indexed": indexed,
        "chunks": total_chunks,
        "errors": errors,
        "skipped": skipped,
    }
    logger.info("reindex_vault: complete – %s", summary)
    return summary
