"""Pandoc AST IR 유틸리티: 이미지 추출, 테이블/캡션 주입, AST→MD 변환."""
from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from typing import Any


def extract_images_from_ast(ast: dict[str, Any]) -> list[dict[str, Any]]:
    """AST를 순회하며 Image 노드 정보를 추출."""
    images: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("t") == "Image":
                content = node.get("c", [])
                if len(content) >= 3:
                    node_id = str(uuid.uuid4())
                    node["_node_id"] = node_id
                    target = content[2]  # [url, title]
                    images.append({
                        "node_id": node_id,
                        "src": target[0] if isinstance(target, list) else str(target),
                        "alt": content[1],
                    })
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(ast)
    return images


def inject_table_into_ast(
    ast: dict[str, Any], node_id: str, md_table: str
) -> dict[str, Any]:
    """Image 노드를 Markdown 테이블 AST로 교체."""
    _md_to_ast_blocks(md_table)

    def _replace(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("_node_id") == node_id:
                return {"t": "RawBlock", "c": ["markdown", md_table]}
            return {k: _replace(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [_replace(item) for item in node]
        return node

    return _replace(ast)


def inject_caption_into_ast(
    ast: dict[str, Any], node_id: str, caption: str
) -> dict[str, Any]:
    """Image 노드의 alt 텍스트를 VLM 생성 캡션으로 교체."""
    def _replace(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("_node_id") == node_id and node.get("t") == "Image":
                content = node["c"]
                if len(content) >= 3:
                    # alt text를 캡션으로 교체
                    content[1] = [{"t": "Str", "c": caption}]
            return {k: _replace(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [_replace(item) for item in node]
        return node

    return _replace(ast)


def _md_to_ast_blocks(md: str) -> list[dict]:
    """짧은 Markdown 조각을 Pandoc AST blocks로 변환."""
    try:
        result = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "json"],
            input=md,
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        return data.get("blocks", [])
    except Exception:
        return []


async def ast_to_markdown(ast: dict[str, Any]) -> str:
    """Pandoc AST JSON → GFM Markdown."""
    def _run():
        ast_str = json.dumps(ast)
        result = subprocess.run(
            ["pandoc", "-f", "json", "-t", "gfm", "--wrap=none"],
            input=ast_str,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Pandoc AST→MD failed: {result.stderr[:500]}")
        return result.stdout

    return await asyncio.to_thread(_run)
