"""Document Ingestion API."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from starlette.responses import StreamingResponse

from backend.dependencies import get_current_user
from backend.config import settings
from backend.ingestion.pipeline import IngestionPipeline
from backend.core.task_manager import task_manager, TaskInfo, TaskStatus

router = APIRouter()
_pipeline = IngestionPipeline()


# ─── 태스크 관리 API ──────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(user_id: str = Depends(get_current_user)):
    return {"tasks": task_manager.list_tasks()}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user_id: str = Depends(get_current_user)):
    info = task_manager.get(task_id)
    if not info:
        return {"error": "Task not found"}
    return info.to_dict()


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str, user_id: str = Depends(get_current_user)):
    ok = task_manager.cancel(task_id)
    if not ok:
        return {"error": "취소할 수 없는 태스크입니다"}
    return {"status": "cancelled", "task_id": task_id}


@router.post("/upload")
async def upload_and_ingest(
    file: UploadFile = File(...),
    dest: str = Form(""),
    user_id: str = Depends(get_current_user),
):
    filename = file.filename or "doc"
    with tempfile.NamedTemporaryFile(
        suffix=Path(filename).suffix,
        delete=False,
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    async def _run(task: TaskInfo):
        task.message = f"변환 중: {filename}"
        task.total = 1
        try:
            rel_path = await _pipeline.ingest(tmp_path, user_id=user_id, dest_rel=dest or None)
            task.progress = 1
            task.result = {"path": rel_path}
            task.message = f"완료: {rel_path}"
        finally:
            tmp_path.unlink(missing_ok=True)

    task_id = task_manager.submit(f"업로드: {filename}", _run)
    return {"status": "accepted", "task_id": task_id}


@router.post("/upload-batch")
async def upload_batch(
    files: list[UploadFile] = File(...),
    dest: str = Form(""),
    relative_paths: str = Form(""),
    user_id: str = Depends(get_current_user),
):
    """폴더 업로드: 여러 파일을 상대 경로 구조를 유지하며 일괄 업로드."""
    # 숨김파일/시스템파일 무시 패턴
    IGNORE_NAMES = {".DS_Store", ".ds_store", "Thumbs.db", "desktop.ini", ".gitkeep"}
    IGNORE_PREFIXES = (".", "__MACOSX")

    rel_path_list = [p.strip() for p in relative_paths.split("\n") if p.strip()] if relative_paths else []

    results: list[dict[str, Any]] = []
    for i, file in enumerate(files):
        filename = file.filename or ""

        # 숨김파일 필터
        basename = Path(filename).name
        if basename in IGNORE_NAMES or any(basename.startswith(p) for p in IGNORE_PREFIXES):
            results.append({"file": filename, "status": "skipped", "error": "Hidden/system file"})
            continue

        # 상대경로 내 숨김 디렉토리 필터 (__MACOSX/..., .hidden/...)
        rel = rel_path_list[i] if i < len(rel_path_list) else ""
        if any(part.startswith(".") or part.startswith("__") for part in Path(rel).parts if part != "."):
            results.append({"file": filename, "status": "skipped", "error": "Hidden directory"})
            continue
        # 폴더 구조 유지: relative_paths가 제공되면 해당 경로 사용
        if i < len(rel_path_list) and rel_path_list[i]:
            file_dest = f"{dest.rstrip('/')}/{rel_path_list[i]}" if dest else rel_path_list[i]
        else:
            file_dest = f"{dest.rstrip('/')}/{file.filename}" if dest else None

        ext = Path(file.filename or "doc").suffix.lower()

        # 마크다운/텍스트는 파이프라인 없이 직접 저장
        if ext in {".md", ".txt", ".yaml", ".yml", ".json"}:
            from backend.core.vault import write_document

            content_bytes = await file.read()
            body = content_bytes.decode("utf-8", errors="replace")
            target = file_dest or f"Public/{file.filename}"
            await write_document(target, body, user_id=user_id)
            results.append({"file": file.filename, "status": "saved", "path": target})
            continue

        # 변환 대상 문서는 파이프라인 처리
        if ext in _pipeline.SUPPORTED_EXTENSIONS:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                content_bytes = await file.read()
                tmp.write(content_bytes)
                tmp_path = Path(tmp.name)

            try:
                # dest_rel에서 확장자를 .md로 변경
                md_dest = str(Path(file_dest).with_suffix(".md")) if file_dest else None
                rel_path = await _pipeline.ingest(tmp_path, user_id=user_id, dest_rel=md_dest)
                results.append({"file": file.filename, "status": "ingested", "path": rel_path})
            except Exception as e:
                results.append({"file": file.filename, "status": "error", "error": str(e)})
            finally:
                tmp_path.unlink(missing_ok=True)
            continue

        # 미지원 포맷
        results.append({"file": file.filename, "status": "skipped", "error": f"Unsupported: {ext}"})

    success = sum(1 for r in results if r["status"] in ("ingested", "saved"))
    return {
        "status": "completed",
        "total": len(files),
        "success": success,
        "errors": len(files) - success,
        "results": results,
    }


@router.post("/reprocess")
async def reprocess_vault_md(
    user_id: str = Depends(get_current_user),
):
    """기존 vault 마크다운 파일들의 HTML 태그를 재처리 (post-process)."""
    import aiofiles
    from backend.config import settings
    from backend.ingestion.markdown_post import post_process
    from backend.core.frontmatter import parse_frontmatter, synthesize_frontmatter

    vault = settings.vault_root
    md_files = list(vault.rglob("*.md"))
    processed = 0
    cleaned = 0

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        cleaned_body = post_process(body)
        if cleaned_body.strip() != body.strip():
            # 프론트매터 보존하며 본문만 교체
            new_content = synthesize_frontmatter(
                cleaned_body, user_id=meta.get("owner", user_id), extra_meta=meta,
            )
            async with aiofiles.open(md_file, "w", encoding="utf-8") as f:
                await f.write(new_content)
            cleaned += 1
        processed += 1

    return {
        "status": "completed",
        "processed": processed,
        "cleaned": cleaned,
        "unchanged": processed - cleaned,
    }


@router.post("/ingest-local")
async def ingest_local_path(
    source_dir: str = Form(...),
    dest: str = Form("Public/"),
    user_id: str = Depends(get_current_user),
):
    """로컬 디렉토리를 백그라운드 태스크로 변환. 페이지 이동해도 계속 실행."""
    source = Path(source_dir)
    if not source.exists() or not source.is_dir():
        return {"error": f"Directory not found: {source_dir}"}

    SUPPORTED = {".pdf", ".docx", ".pptx", ".hwp", ".hwpx", ".doc"}
    TEXT_EXTS = {".md", ".txt", ".yaml", ".yml", ".json"}
    IGNORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

    async def _run(task: TaskInfo):
        from backend.core.vault import write_document

        task.message = "파일 스캔 중..."

        all_files = await asyncio.to_thread(
            lambda: [
                f for f in source.rglob("*")
                if f.is_file()
                and f.name not in IGNORE_NAMES
                and not f.name.startswith(".")
                and not any(p.startswith(".") or p.startswith("__") for p in f.relative_to(source).parts[:-1])
            ]
        )
        task.total = len(all_files)
        task.message = f"{task.total}개 파일 변환 시작"
        task.result = {"success": 0, "errors": 0, "skipped": 0}

        for file_path in all_files:
            # 취소 확인
            if task.status == TaskStatus.CANCELLED:
                break

            rel = file_path.relative_to(source)
            target_rel = f"{dest.rstrip('/')}/{rel}"
            ext = file_path.suffix.lower()
            task.progress += 1
            task.message = str(rel)

            try:
                if ext in TEXT_EXTS:
                    body = file_path.read_text(encoding="utf-8", errors="replace")
                    await write_document(target_rel, body, user_id=user_id)
                    task.result["success"] += 1

                elif ext in SUPPORTED:
                    md_target = str(Path(target_rel).with_suffix(".md"))
                    try:
                        await _pipeline.ingest(file_path, user_id=user_id, dest_rel=md_target)
                        task.result["success"] += 1
                    except Exception:
                        fallback_text = await _fallback_convert(file_path, ext)
                        if fallback_text:
                            from backend.ingestion.markdown_post import post_process
                            cleaned = post_process(fallback_text)
                            await write_document(md_target, cleaned, user_id=user_id, extra_meta={"source_format": ext, "fallback": True})
                            task.result["success"] += 1
                        else:
                            task.result["errors"] += 1
                else:
                    task.result["skipped"] += 1

            except Exception:
                task.result["errors"] += 1

            if task.progress % 10 == 0:
                await asyncio.sleep(0)

        s = task.result
        task.message = f"완료: {s['success']}건 성공, {s['errors']}건 실패, {s['skipped']}건 건너뜀"

    task_id = task_manager.submit(f"로컬 인제스트: {source_dir}", _run)
    return {"status": "accepted", "task_id": task_id}


@router.post("/pdf-to-docx")
async def convert_pdf_to_docx(
    file: UploadFile = File(...),
    dest: str = Form(""),
    user_id: str = Depends(get_current_user),
):
    """PDF → DOCX → 마크다운 → 그래프 적재 (백그라운드 태스크)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"error": "PDF 파일만 지원합니다"}

    filename = file.filename
    doc_name = Path(filename).stem

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_in:
        content = await file.read()
        tmp_in.write(content)
        pdf_path = Path(tmp_in.name)

    async def _run(task: TaskInfo):
        docx_path = pdf_path.with_suffix(".docx")
        try:
            # Step 1: PDF → DOCX
            task.total = 3
            task.message = "PDF → DOCX 변환 중..."
            from pdf2docx import Converter

            def _convert():
                cv = Converter(str(pdf_path))
                cv.convert(str(docx_path))
                cv.close()

            await asyncio.to_thread(_convert)
            task.progress = 1

            if not docx_path.exists():
                raise RuntimeError("DOCX 변환 실패")

            # Step 2: DOCX → 마크다운
            task.message = "마크다운 변환 중..."
            rel_path = dest or f"Public/{doc_name}.md"
            md_path = await _pipeline.ingest(docx_path, user_id=user_id, dest_rel=rel_path)
            task.progress = 2
            task.result["path"] = md_path

            # Step 3: 그래프 적재
            task.message = "지식그래프 적재 중..."
            try:
                from backend.graph.extractor import GraphExtractor
                from backend.graph.store import GraphStore

                persist_path = settings.vault_root / ".graph" / "knowledge_graph.json"
                store = GraphStore(persist_path=persist_path)
                extractor = GraphExtractor(graph_store=store)

                md_full_path = settings.vault_root / rel_path.lstrip("/")
                if md_full_path.exists():
                    entities, relationships = await extractor.extract_from_file(
                        md_full_path, f"/{rel_path.lstrip('/')}"
                    )
                    store.save()
                    task.result["graph"] = {
                        "entities": len(entities),
                        "relationships": len(relationships),
                    }
            except Exception as e:
                task.result["graph"] = {"error": str(e)}

            task.progress = 3
            task.message = f"완료: {md_path}"
        finally:
            pdf_path.unlink(missing_ok=True)
            docx_path.unlink(missing_ok=True)

    task_id = task_manager.submit(f"PDF 변환: {filename}", _run)
    return {"status": "accepted", "task_id": task_id}


def _sse(data: dict) -> str:
    """SSE 형식으로 JSON 이벤트 생성."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _fallback_convert(file_path: Path, ext: str) -> str | None:
    """Marker 실패 시 폴백 변환 체인: pdf2docx → pandoc → pdftotext → OCR."""
    import subprocess
    import shutil
    import tempfile

    # 1단계: pandoc 직접 변환 (DOCX/PPTX에 유효)
    if ext in {".docx", ".pptx", ".doc"}:
        try:
            result = subprocess.run(
                ["pandoc", str(file_path), "-t", "gfm", "--wrap=none"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception:
            pass

    # PDF 전용 폴백
    if ext != ".pdf":
        return None

    # 2단계: pdf2docx → pandoc (별도 프로세스로 격리, 60초 타임아웃)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docx_path = tmp_path / "converted.docx"
            script = f"""
import sys
from pdf2docx import Converter
cv = Converter(sys.argv[1])
cv.convert(sys.argv[2])
cv.close()
"""
            proc = subprocess.run(
                [sys.executable, "-c", script, str(file_path), str(docx_path)],
                capture_output=True, timeout=60,
            )

            if proc.returncode == 0 and docx_path.exists():
                result = subprocess.run(
                    ["pandoc", str(docx_path), "-t", "gfm", "--wrap=none"],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0 and result.stdout.strip():
                    text = result.stdout.strip()
                    alpha_count = sum(1 for c in text if c.isalpha())
                    if alpha_count > 100:
                        return f"# {file_path.stem}\n\n{text}"
    except subprocess.TimeoutExpired:
        import logging
        logging.getLogger(__name__).warning("pdf2docx timed out for %s", file_path.name)
    except Exception:
        pass

    # 3단계: pdftotext (텍스트 레이어가 있는 PDF)
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(file_path), "-"],
                capture_output=True, text=True, timeout=30,
            )
            text = result.stdout.strip()
            alpha_count = sum(1 for c in text if c.isalpha())
            if alpha_count > 100:
                from backend.ingestion.markdown_post import convert_layout_tables
                text = convert_layout_tables(text)
                return f"# {file_path.stem}\n\n{text}"
        except Exception:
            pass

    # 4단계: OCR (스캔 이미지 PDF) — pdftoppm + tesseract
    if shutil.which("pdftoppm") and shutil.which("tesseract"):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "200", str(file_path), str(tmp_path / "page")],
                    capture_output=True, timeout=120,
                )
                pages = sorted(tmp_path.glob("page-*.png"))
                if not pages:
                    return None

                all_text: list[str] = []
                for page_img in pages:
                    result = subprocess.run(
                        ["tesseract", str(page_img), "stdout", "-l", "kor+eng", "--psm", "6"],
                        capture_output=True, text=True, timeout=60,
                    )
                    page_text = result.stdout.strip()
                    if page_text:
                        all_text.append(page_text)

                if all_text:
                    combined = "\n\n---\n\n".join(all_text)
                    return f"# {file_path.stem}\n\n{combined}"
        except Exception:
            pass

    return None
