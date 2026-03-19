# MaLife Lake - Secure Agentic RAG

## Project Overview
금융/보험 도메인의 Git-backed Markdown 기반 자율형 보안 RAG 및 Multi-Agent 시스템 MVP 백엔드.
이기종 문서(HWP, PDF, PPTX)를 AI 친화적 마크다운으로 변환하고, 개인/공용 자료를 안전하게 통합 분석하는 Agentic RAG 플랫폼.

## Architecture Principles
- **No App Dependency**: Obsidian 등 에디터 불필요. 순수 Markdown 파일 + YAML frontmatter + [[위키링크]] = DB
- **Git-backed**: Vault 폴더는 Git 형상관리. 파일 조작 시 자동 커밋
- **Configuration as Code**: RDBMS 없이 `vault/iam.yaml`로 RBAC + Ownership 통제
- **Pandoc AST IR**: 이기종 문서 → Pandoc AST(JSON) 중간계층 → GFM Markdown (직접 포맷 변환 금지)
- **VLM Pipeline**: 문서 내 이미지 → 표(table)이면 MD 표 복원, 다이어그램이면 시맨틱 캡션 생성
- **ACL-enforced Vector Search**: ChromaDB 메타데이터에 allowed_roles + owner 삽입 → $or 필터 강제

## Tech Stack
- Python 3.11+, FastAPI (async), LangGraph (State & Orchestration), LangChain
- ChromaDB (Vector DB), SQLite (LangGraph Checkpointer)
- Pydantic v2, Pandoc, Marker (PDF Layout), Vision LLM API (gpt-4o-mini)
- GitPython, python-frontmatter, aiofiles, httpx

## Directory Layout
```
backend/
  main.py              # FastAPI entry (lifespan, DLP middleware)
  config.py            # pydantic-settings
  dependencies.py      # DI: get_current_user, get_iam
  core/                # IAM, Vault I/O, Workspace ACL, Frontmatter
  ingestion/           # Pandoc AST pipeline, VLM processor, MD post-processor
    converters/        # PDF(Marker), HWP(LibreOffice/hwp5txt), Office(Pandoc native)
  indexer/             # Chunker, ChromaDB vectorstore, Secure search
  agents/              # LangGraph graph, Skill parser, Nodes, Checkpointer
  adapters/            # Legacy system adapter (async isolation)
  security/            # DLP/PII masking, Prompt injection guard, Kill switch
  admin/               # IAM CRUD + Audit log API
  routers/             # 5 API routers (vault, ingest, search, agent, legacy)
vault/                 # Data Lake (Markdown files)
  iam.yaml             # RBAC configuration
  Public/              # 공용 문서
  Private/{user_id}/   # 개인 워크스페이스
  Skills/              # type:skill 마크다운 → LangChain Tool 동적 변환
```

## Key Conventions
- All API auth via `X-User-Id` header → IAM engine resolves roles
- Private workspace: `vault/Private/{user_id}/` — 타인 접근 원천 차단
- Skill markdown: frontmatter에 `type: skill`, `skill_name`, `endpoint`, `depends_on` 필수
- PII masking: 응답 미들웨어에서 주민번호/전화번호/카드번호/이메일 자동 마스킹
- LangGraph state: user_id, skill chain, I/O payload, reasoning 완전 기록
- Legacy adapter: 동기 호출을 asyncio.to_thread로 격리, 에러코드→자연어 변환

## Running
```bash
cp .env.example .env  # API 키 설정
pip install -e ".[dev]"
uvicorn backend.main:app --reload --port 9001
```

## Testing
```bash
pytest tests/ -v
```
