# MaLife Lake — Secure Agentic RAG

> 금융/보험 도메인의 Git-backed Markdown 기반 자율형 보안 RAG 및 Multi-Agent 시스템

## 프로젝트 목표

**이기종 문서를 AI가 이해할 수 있는 형태로 전환하고, 안전하게 분석·행동할 수 있는 플랫폼을 구축한다.**

보험사 현업에는 HWP, PDF, PPTX 등 다양한 포맷의 사업방법서, 약관, 내부 규정이 산재되어 있다. 이 문서들은 서로 다른 시스템에 분산 저장되어 있고, 검색·분석·활용이 어렵다.

MaLife Lake는 이 문제를 다음과 같이 해결한다:

### 1. 문서 통합 (Universal Ingestion)
- HWP, PDF(OCR 포함), PPTX, DOCX → **Pandoc AST 중간 계층** → 규격화된 GFM Markdown
- 이미지 내 표는 VLM으로 복원, 다이어그램은 시맨틱 캡션 생성
- Git으로 모든 변경 이력 추적

### 2. 보안 데이터 레이크 (Secure Data Lake)
- **Obsidian 불필요** — 순수 Markdown + YAML Frontmatter + `[[위키링크]]` = 데이터베이스
- `iam.yaml` 기반 **Configuration as Code** (RBAC + Ownership)
- Public/Private 워크스페이스 물리 분리, 벡터 검색 시 ACL 필터 강제

### 3. 지식그래프 & GraphRAG
- LLM 기반 엔티티/관계 자동 추출 → NetworkX 지식그래프 구축
- **GraphRAG**: 벡터 검색 + 그래프 순회를 결합한 하이브리드 검색
  - Local: 엔티티 매칭 → 이웃 순회 → 문서 수집
  - Global: Louvain 커뮤니티 요약 기반 컨텍스트
  - Hybrid: 두 방식 결합
- Force-directed 그래프 시각화

### 4. Multi-Agent 오케스트레이션
- **LangGraph** 기반 상태 관리: `guard → route → plan → execute → audit → respond`
- Skill Registry: Markdown frontmatter에서 `type: skill` 정의 → LangChain Tool 동적 변환
- 의존성 위상정렬 (Kahn's Algorithm)으로 스킬 체인 자동 실행
- SQLite Checkpointer로 실행자·스킬·입출력·판단 논리 완전 감사

### 5. 보안 & 컴플라이언스 (CISO)
- **PII 마스킹**: 주민번호, 전화번호, 카드번호, 사업자번호 등 8종 자동 마스킹
- **Prompt Injection 방어**: 한국어/영어 인젝션 + 탈옥 패턴 18종 탐지
- **Kill Switch**: 긴급 차단 + 타임아웃 자동 해제 + 이벤트 이력

## 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI (async), Pydantic v2 |
| AI/ML | LangGraph, LangChain, ChatOpenAI, ChromaDB |
| Graph | NetworkX, rapidfuzz, Louvain Community Detection |
| Document | Pandoc, Marker (PDF), Tesseract OCR, VLM API |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Framer Motion |
| Visualization | react-force-graph-2d (Knowledge Graph) |
| Storage | Git (형상관리), SQLite (Checkpointer), JSON (Graph) |

## 디렉토리 구조

```
backend/
  core/          # IAM, Vault, Workspace, Frontmatter
  ingestion/     # Pandoc AST 파이프라인, VLM, Converters (PDF/HWP/Office)
  indexer/       # Chunker, ChromaDB, Secure Search
  agents/        # LangGraph Orchestrator, Skill Parser, Nodes
  graph/         # Knowledge Graph Store, Extractor, GraphRAG Engine
  adapters/      # Legacy System Adapter
  security/      # DLP, Prompt Guard, Kill Switch
  admin/         # IAM CRUD, Audit Log API
  routers/       # REST API (vault, ingest, search, agent, graph, legacy)
frontend/
  src/pages/     # Dashboard, Vault, Agent, Ingest, Search, Graph, Admin
vault/           # Markdown Data Lake (Git-backed)
  iam.yaml       # RBAC Configuration
  Public/        # 공용 문서
  Private/       # 개인 워크스페이스
  Skills/        # type:skill 마크다운 → Tool 변환
tests/           # pytest (IAM, DLP, Chunker, Skill Parser 등)
```

## 실행 방법

```bash
# 백엔드
cp .env.example .env  # API 키 설정
pip install -e ".[dev]"
uvicorn backend.main:app --reload --port 9001

# 프론트엔드
cd frontend && npm install && npm run dev  # → http://localhost:9000
```

## API 엔드포인트

| Prefix | 설명 |
|--------|------|
| `/api/v1/vault/*` | 문서 CRUD, 파일/폴더 삭제 |
| `/api/v1/ingest/*` | 문서 업로드, 배치 업로드, 로컬 인제스트 (SSE) |
| `/api/v1/search/` | ACL 기반 시맨틱/하이브리드 검색 |
| `/api/v1/agent/run` | Multi-Agent 실행 |
| `/api/v1/graph/*` | 지식그래프 CRUD, GraphRAG 검색 |
| `/api/v1/admin/*` | IAM 관리, 감사 로그, Kill Switch |

## 라이선스

Private — 미래에셋생명 내부 프로젝트
