---
name: MaLife Lake 프로젝트 개요
description: 금융/보험 Secure Agentic RAG MVP 백엔드 - 기술 스택, 아키텍처, 진행 상태
type: project
---

MaLife Lake는 금융/보험 도메인의 Git-backed Markdown 기반 자율형 보안 RAG & Multi-Agent 시스템 MVP 백엔드.

**Why:** 사내 이기종 문서(HWP, PDF, PPTX)와 비즈니스 룰을 AI 친화적으로 전환하여 개인/공용 자료를 안전하게 통합 분석+행동(Command)하는 Agentic RAG 플랫폼 구축.

**How to apply:** 모든 코드는 FastAPI + LangGraph + ChromaDB 기반. Obsidian 의존 없이 순수 Markdown + YAML frontmatter + [[위키링크]]만 사용. iam.yaml 기반 RBAC 강제.

핵심 모듈 9개: IAM, Vault, Ingestion(Pandoc AST IR+VLM), Indexer(ACL 벡터검색), Skill Registry(위상정렬), LangGraph Orchestrator(guard→route→plan→execute→audit→respond), Legacy Adapter, Security(DLP/PII/Kill Switch), Admin API.

2026-03-19 기준: MVP 스캐폴딩 + 상세 구현 + 테스트 142건 + 코드리뷰 완료. 2 commits on main.
