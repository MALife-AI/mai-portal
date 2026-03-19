"""YAML Frontmatter 파싱 및 합성."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import frontmatter


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    post = frontmatter.loads(content)
    return dict(post.metadata), post.content


def synthesize_frontmatter(
    body: str,
    *,
    user_id: str,
    extra_meta: dict | None = None,
) -> str:
    existing_meta, existing_body = parse_frontmatter(body)
    meta = {
        "owner": user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **existing_meta,
        **(extra_meta or {}),
    }
    if "created_at" not in meta:
        meta["created_at"] = meta["updated_at"]

    post = frontmatter.Post(existing_body, **meta)
    return frontmatter.dumps(post) + "\n"
