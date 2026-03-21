# MaLife Lake - Secure Agentic RAG

## Project Overview
금융/보험 도메인의 Git-backed Markdown 기반 자율형 보안 RAG 및 Multi-Agent 시스템.
이기종 문서(HWP, PDF, PPTX)를 AI 친화적 마크다운으로 변환하고, 개인/공용 자료를 안전하게 통합 분석하는 Agentic RAG 플랫폼.

## Architecture Principles
- **No App Dependency**: 순수 Markdown 파일 + YAML frontmatter + [[위키링크]] = DB
- **Git-backed**: Vault 폴더는 Git 형상관리. 파일 조작 시 자동 커밋
- **Configuration as Code**: RDBMS 없이 `vault/iam.yaml`로 RBAC + Ownership + Department 통제
- **Pandoc AST IR**: 이기종 문서 → Pandoc AST(JSON) 중간계층 → GFM Markdown
- **Smart PDF Pipeline**: pdftotext(텍스트 확인) → pdf2docx(텍스트 PDF) / OCR(스캔 PDF)
- **VLM Pipeline**: 문서 내 이미지 → 표(table)이면 MD 표 복원, 다이어그램이면 시맨틱 캡션 생성
- **ACL-enforced Vector Search**: ChromaDB 메타데이터에 allowed_roles + owner 삽입 → $or 필터 강제
- **Unsloth + llama.cpp**: GGUF 양자화 모델 + Metal GPU 가속 + OpenAI 호환 API

## Tech Stack
- **Backend**: Python 3.11+, FastAPI (async), LangGraph, LangChain
- **Frontend**: React 18 + Vite + TailwindCSS + Framer Motion + Recharts
- **LLM Inference**: llama-server (llama.cpp Metal) + Unsloth GGUF, OpenAI 호환 API
- **Vector DB**: ChromaDB, **Graph DB**: NetworkX + JSON persistence
- **Document**: Pandoc, pdf2docx, Tesseract OCR, pdftotext
- **Storage**: Git-backed Markdown vault, SQLite (checkpointer)

## Directory Layout
```
backend/
  main.py              # FastAPI entry (lifespan, DLP middleware)
  config.py            # pydantic-settings (.env 기반)
  dependencies.py      # DI: get_current_user, get_iam, require_admin
  core/                # IAM, Vault I/O, Workspace ACL, Frontmatter, TaskManager
  ingestion/           # Pandoc AST pipeline, VLM processor, MD post-processor
    converters/        # PDF(pdf2docx+OCR), HWP(LibreOffice), Office(Pandoc native)
  indexer/             # Chunker (page marker aware), ChromaDB vectorstore, Secure search
  agents/              # LangGraph graph, Skill parser, Nodes, LLM factory, Checkpointer
  graph/               # Knowledge Graph: store, extractor, graphrag engine, models
  adapters/            # Legacy system adapter (async isolation)
  security/            # DLP/PII masking, Prompt injection guard, Kill switch
  admin/               # IAM CRUD, Audit log, Model config, Metrics, Governance, Infra
  routers/             # API routers (vault, ingest, search, agent, legacy, graph, skill)
frontend/
  src/pages/           # Dashboard, VaultExplorer, AgentConsole, Ingestion, Search,
                       # KnowledgeGraph, Skills, Admin
  src/components/      # Layout, Sidebar, TaskBar, GraphOverlay, MarkdownViewer, Toast, Modal
  src/api/client.ts    # Typed API client (REST + SSE streaming)
  src/store/useStore.ts # Zustand global state
data/
  skills/              # Skill 마크다운 정의 (vault 밖)
  gpu_servers.json     # GPU 추론 서버 목록
  permissions.json     # 세분화된 사용자 권한
vault/                 # Data Lake (Markdown files)
  iam.yaml             # RBAC + Department configuration
  Public/              # 공용 문서
  Private/{user_id}/   # 개인 워크스페이스
infra/
  Dockerfile.inference # GPU 추론 서버 컨테이너 (CUDA/CPU)
  docker-compose.inference.yml
  deploy.sh            # 로컬/원격 배포 스크립트
```

## Key Conventions
- All API auth via `X-User-Id` header → IAM engine resolves roles + department
- Private workspace: `vault/Private/{user_id}/` — 타인 접근 원천 차단
- Skills: `data/skills/` 디렉토리 (vault 밖), frontmatter에 `type: skill` 필수
- PII masking: 응답 미들웨어에서 주민번호/전화번호/카드번호/이메일 자동 마스킹
- SSRF protection: `server_url`은 `gpu_servers.json` 허용 목록으로 검증
- Document versioning: frontmatter `effective_date` + 파일명 날짜 패턴 자동 추출
- Department-aware: 사용자 소속에 따라 관련 사규/매뉴얼 우선 참조

## LLM Provider Configuration (.env)
```bash
VLM_PROVIDER=llama_server        # llama_server | ollama | claude_wrapper | openai
VLM_MODEL=qwen3.5-4b
LLAMA_SERVER_URL=http://localhost:8801/v1
# Smart routing (optional)
SMART_ROUTING=false
LLAMA_SERVER_LIGHT=http://localhost:8801/v1
LLAMA_SERVER_HEAVY=http://gpu-server:8801/v1
```

## Running
```bash
# 1. LLM inference server (Unsloth GGUF + Metal)
llama-server --model ~/.cache/huggingface/hub/models--unsloth--Qwen3.5-4B-GGUF/.../Qwen3.5-4B-Q8_0.gguf \
  --alias qwen3.5-4b --ctx-size 16384 --n-gpu-layers 999 --port 8801 --jinja

# 2. Backend
source .venv/bin/activate
uvicorn backend.main:app --reload --port 9001

# 3. Frontend
cd frontend && npx vite --port 5173
```

## Agent Architecture
```
사용자 질문
  ↓
GraphRAG 컨텍스트 검색 (hybrid: vector + graph)
  ↓ 출처 노드 + 번호 매긴 컨텍스트 주입
llama-server (OpenAI tool calling, --jinja)
  ↓ auto-healing loop (최대 5회)
  ├── 텍스트 → SSE 스트리밍 토큰
  └── tool call → 스킬 실행 → 결과 재주입
  ↓
인라인 인용 [1][2] + 출처 목록
```

## PDF Ingestion Pipeline
```
PDF 업로드
  ↓ pdftotext로 한글 텍스트 확인
  ├── 한글 50자+ (텍스트 PDF) → pdf2docx → DOCX → Pandoc → 마크다운
  └── 한글 50자- (스캔 PDF) → OCR(pdftoppm+tesseract) → 마크다운
  ↓ <!-- page:N --> 마커 삽입
vault 저장 + 그래프 엔티티 추출 (effective_date 포함)
```

## Fine-grained Permissions (22개)
```
문서 관리: doc.read.public, doc.read.private, doc.read.all_private,
          doc.write.public, doc.write.private, doc.delete, doc.upload, doc.upload.public
에이전트:  agent.query, agent.skill.use, agent.skill.manage
검색:      search.vector, search.graphrag
지식그래프: graph.view, graph.build
관리:      admin.iam, admin.model, admin.metrics, admin.audit,
          admin.governance, admin.infra, admin.killswitch
```

## Testing
```bash
pytest tests/ -v
```
