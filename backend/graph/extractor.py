"""GraphExtractor: 보험 도메인 특화 엔티티/관계 추출기.

claude-code-api-wrapper를 LLM 백엔드로 사용.
상품설계·상담·클레임·언더라이팅에 필요한 프로퍼티를 구조적으로 추출합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from backend.config import settings
from backend.graph.models import Entity, Relationship
from backend.graph.store import GraphStore

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 3000
_MAX_CONCURRENCY = 4

_EXTRACTION_PROMPT = """\
당신은 보험 도메인 지식그래프 전문 추출기입니다.
다음 보험 약관/사업방법서/산출방법서 텍스트에서 엔티티와 관계를 추출하여 JSON으로 반환하세요.

## 엔티티 타입 & 추출할 프로퍼티

1. **product** (보험상품/특약)
   - product_code: 상품코드 (예: "A3756")
   - rider_code: 보종코드 (예: "85044")
   - coverage_amount: 보장금액 (예: "3000만원")
   - coverage_period: 보장기간 (예: "90세만기", "100세만기", "종신")
   - payment_period: 보험료납입기간 (예: "10년납", "20년납")
   - payment_frequency: 납입주기 (예: "월납")
   - waiting_period: 면책/감액기간 (예: "90일")
   - renewal_type: "갱신형" 또는 "비갱신형"
   - age_range: 가입연령 (예: "15세~75세")
   - underwriting_class: 심사등급 (예: "간편고지", "간편고지형(0)~(5)", "표준체")
   - premium_type: 보험료유형 (예: "자연식", "평준")
   - surrender_type: 해약환급금 유형 ("기본형", "해약환급금이 없는 유형")
   - surrender_ratio: 해약환급금 비율 (예: "기본형의 50%")
   - base_amount: 기준가입금액 (예: "10만원")
   - sub_types: 세부유형 (예: "1종~5종")
   - parent_product: 종속된 주계약명 (특약인 경우)
   - effective_date: 시행일 (YYYY-MM 또는 "2504" → "2025-04")
   - document_type: 출처 문서유형 ("약관", "사업방법서", "산출방법서")

2. **coverage** (보장항목: 진단금, 수술비, 입원비 등)
   - coverage_amount: 지급금액
   - claim_conditions: 지급조건 (예: "최초1회한", "수술1회당", "1일이상 120일한도")
   - exclusions: 면책사항
   - duplicate_surgery_rule: 중복수술 시 지급규칙 (예: "가장 높은 금액 한 종류만")

3. **condition** (질병/상해: 암, 뇌혈관질환, 심장질환 등)
   - icd_code: 질병코드 (예: "C73")
   - severity: 중증도 분류 (예: "일반암", "소액암", "고액암")

4. **regulation** (규정/법령/약관조항)
   - effective_date: 시행일
   - article_number: 조항번호 (예: "제3조")

5. **organization** (회사/기관)
6. **term** (전문용어/정의)
   - definition: 정의 내용

7. **document** (문서/자료)
   - document_type: "약관", "사업방법서", "산출방법서"
   - effective_date: 시행일/개정일

8. **actuarial** (보험수리/산출 관련)
   - rate_reference: 적용위험률 출처 (예: "보험개발원 생명장기 제2024-307호")
   - expense_ratio: 사업비율 (예: "α_p=75%")
   - lapse_rate: 적용해지율 관련

## 관계 타입
- covers: 보장 (상품→보장항목/질병)
- includes: 포함 (주계약→종속특약)
- excludes: 면책/제외 (상품→질병)
- requires: 가입요건/의무동시가입
- depends_on: 의존
- regulates: 규제 (법령→상품)
- belongs_to: 소속 (특약→주계약)
- references: 참조
- provides: 제공
- defines: 정의 (약관→용어)
- diagnoses: 진단관련
- pays: 지급 (보장항목→금액)
- renews_as: 갱신관계
- supersedes: 대체 (신규→구버전)
- must_coexist: 의무동시가입 (특약↔특약)
- converts_to: 전환 (간편고지→일반심사)

## 출력 형식 (유효한 JSON만 반환)
{{
  "entities": [
    {{
      "name": "엔티티명",
      "type": "엔티티타입",
      "description": "간략한 설명",
      "properties": {{
        ...해당하는 프로퍼티만 포함
      }}
    }}
  ],
  "relationships": [
    {{"source": "소스", "target": "타겟", "type": "관계타입", "description": "관계설명"}}
  ]
}}

## 추출 지침
- 보험 상품명/특약명은 정확하게 추출 (예: "1-5종수술특약(간편고지)")
- 상품코드(A3756), 보종코드(85044) 등 코드 값 반드시 추출
- 금액, 기간, 조건 등 정량적 정보를 properties에 반드시 포함
- 면책사항, 감액기간, 지급제한, 중복수술규칙 등 클레임 관련 정보 우선 추출
- 주계약↔종속특약 관계, 의무동시가입 관계 반드시 추출
- 해약환급금 유형(기본형/해약환급금이 없는 유형)과 비율 추출
- 약관 버전 코드(예: _2504)가 있으면 effective_date로 변환 (2504 → "2025-04")
- 산출방법서의 사업비율, 적용위험률 출처 추출
- content_type: 엔티티가 추출된 원본 콘텐츠 유형을 반드시 명시
  - "text": 일반 텍스트/문장에서 추출
  - "table": 표(테이블)에서 추출
  - "list": 목록/항목에서 추출
  - "formula": 수식/산출식에서 추출
  - "image": 이미지/다이어그램 캡션에서 추출

텍스트:
{text}
"""

_EXTRACTION_PROMPT_WITH_HINTS = """\
당신은 보험 도메인 지식그래프 전문 추출기입니다.
다음 보험 약관/사업방법서/산출방법서 텍스트에서 엔티티와 관계를 추출하세요.

## 엔티티 타입 & 주요 프로퍼티
1. **product** - product_code, rider_code, coverage_amount, coverage_period, payment_period,
   payment_frequency, waiting_period, renewal_type, age_range, underwriting_class,
   premium_type, surrender_type, surrender_ratio, base_amount, sub_types, parent_product,
   effective_date, document_type
2. **coverage** - coverage_amount, claim_conditions, exclusions, duplicate_surgery_rule
3. **condition** - icd_code, severity
4. **regulation** - effective_date, article_number
5. **organization**
6. **term** - definition
7. **document** - document_type, effective_date
8. **actuarial** - rate_reference, expense_ratio, lapse_rate

## 이미 알려진 엔티티 (동일 개체는 아래 이름 그대로 사용):
{existing_entities}

## 관계 타입
covers, includes, excludes, requires, depends_on, regulates, belongs_to,
references, provides, defines, diagnoses, pays, renews_as, supersedes,
must_coexist, converts_to

## 출력: 유효한 JSON만 반환
{{
  "entities": [{{"name":"","type":"","description":"","properties":{{}}}}],
  "relationships": [{{"source":"","target":"","type":"","description":""}}]
}}

텍스트:
{text}
"""


_ALLOWED_PROPERTIES = (
    # product
    "product_code", "rider_code", "coverage_amount", "coverage_period",
    "payment_period", "payment_frequency", "waiting_period", "renewal_type",
    "age_range", "underwriting_class", "premium_type", "surrender_type",
    "surrender_ratio", "base_amount", "sub_types", "parent_product",
    "effective_date", "document_type",
    # coverage
    "claim_conditions", "exclusions", "duplicate_surgery_rule",
    # condition
    "icd_code", "severity",
    # regulation
    "article_number",
    # term
    "definition",
    # actuarial
    "rate_reference", "expense_ratio", "lapse_rate",
    # common
    "premium_exemption", "mandatory_riders", "conversion_period", "revival_period",
    # content origin
    "content_type",  # text | table | image | formula | list | diagram
)


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w가-힣]", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "entity"


def _split_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) > chunk_size and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(para)
        current_len += len(para)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks or [text[:chunk_size]]


def _parse_extraction_response(raw: str) -> dict[str, Any]:
    text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.debug("_parse_extraction_response: could not parse: %.200s", raw)
    return {"entities": [], "relationships": []}


def _extract_wikilinks(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"\[\[([^\]]+)\]\]", text)]


def _extract_page_range(text: str) -> tuple[int | None, int | None]:
    """텍스트에서 <!-- page:N --> 마커를 찾아 (시작페이지, 끝페이지) 반환."""
    pages = [int(m.group(1)) for m in re.finditer(r"<!--\s*page:(\d+)\s*-->", text)]
    if not pages:
        return (None, None)
    return (min(pages), max(pages))


def _extract_source_doc_name(source_path: str) -> str:
    """출처 문서명 추출 (경로에서 파일명만)."""
    return Path(source_path).stem


class GraphExtractor:
    """보험 도메인 특화 지식그래프 엔티티/관계 추출기."""

    def __init__(
        self,
        graph_store: GraphStore,
        model: str | None = None,
    ) -> None:
        self._store = graph_store
        self._model = model or settings.vlm_model
        self._llm: Any = None
        self._use_wrapper = settings.vlm_provider == "claude_wrapper"
        self._http_client: httpx.AsyncClient | None = None

    def _get_llm(self) -> Any:
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                model=self._model,
                api_key=settings.openai_api_key,
                temperature=0,
            )
        return self._llm

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=settings.claude_wrapper_url,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        return self._http_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_from_text(
        self,
        text: str,
        source_path: str,
        effective_date: str | None = None,
    ) -> tuple[list[Entity], list[Relationship]]:
        passages = _split_text(text)
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _extract_passage(passage: str) -> dict[str, Any]:
            async with sem:
                return await self._call_llm(passage)

        raw_results = await asyncio.gather(*[_extract_passage(p) for p in passages])

        all_entities: list[Entity] = []
        all_relationships: list[Relationship] = []

        for passage, result in zip(passages, raw_results):
            page_range = _extract_page_range(passage)
            ents, rels = self._build_graph_objects(result, source_path, page_range=page_range, effective_date=effective_date)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        for entity in all_entities:
            self._store.add_entity(entity)
        for rel in all_relationships:
            self._store.add_relationship(rel)

        logger.info(
            "GraphExtractor: %s → %d entities, %d relationships",
            source_path, len(all_entities), len(all_relationships),
        )
        return all_entities, all_relationships

    async def extract_from_document(
        self,
        content: str,
        source_path: str,
        existing_entities: list[str] | None = None,
    ) -> tuple[list[Entity], list[Relationship]]:
        """단일 문서에서 엔티티/관계 추출 (기존 엔티티 힌트 포함)."""
        passages = _split_text(content)
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _extract_passage(passage: str) -> dict[str, Any]:
            async with sem:
                return await self._call_llm(passage, existing_entities=existing_entities)

        raw_results = await asyncio.gather(*[_extract_passage(p) for p in passages])

        all_entities: list[Entity] = []
        all_relationships: list[Relationship] = []

        for result in raw_results:
            ents, rels = self._build_graph_objects(result, source_path)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        logger.info(
            "extract_from_document: %s → %d entities, %d rels",
            source_path, len(all_entities), len(all_relationships),
        )
        return all_entities, all_relationships

    async def extract_from_wikilinks(
        self,
        content: str,
        source_path: str,
    ) -> list[Relationship]:
        """[[위키링크]]에서 문서 간 구조적 참조 관계 추출."""
        links = _extract_wikilinks(content)
        if not links:
            return []

        source_name = _extract_source_doc_name(source_path)
        source_id = _slugify(source_name)

        source_entity = Entity(
            id=source_id,
            name=source_name,
            entity_type="document",
            properties={"source_document": source_path},
            source_paths=[source_path],
            mentions=1,
        )
        self._store.add_entity(source_entity)

        relationships: list[Relationship] = []
        for link in links:
            target_id = _slugify(link)
            target_entity = Entity(
                id=target_id,
                name=link,
                entity_type="document",
                source_paths=[source_path],
                mentions=1,
            )
            self._store.add_entity(target_entity)

            rel = Relationship(
                source_id=source_id,
                target_id=target_id,
                relation_type="references",
                properties={"via": "wikilink"},
                source_path=source_path,
                weight=1.0,
            )
            relationships.append(rel)

        return relationships

    async def extract_from_file(self, file_path: Path, rel_path: str) -> tuple[list[Entity], list[Relationship]]:
        # Skills, 설정 파일 등은 그래프 적재 대상이 아님
        rel_parts = Path(rel_path).parts
        if any(ex in rel_parts for ex in self._EXCLUDE_DIRS):
            logger.debug("Skipping excluded path: %s", rel_path)
            return [], []
        if file_path.name in self._EXCLUDE_FILES:
            logger.debug("Skipping excluded file: %s", file_path.name)
            return [], []

        content = await asyncio.to_thread(file_path.read_text, "utf-8")

        # frontmatter에서 effective_date 추출
        effective_date = None
        try:
            from backend.core.frontmatter import parse_frontmatter
            meta, body = parse_frontmatter(content)
            effective_date = meta.get("effective_date") or meta.get("updated_at", "")[:10] or None
            # 파일명에서 날짜 추출 시도 (예: _약관_20220101.md)
            if not effective_date:
                import re
                date_match = re.search(r'(\d{8})', file_path.stem)
                if date_match:
                    d = date_match.group(1)
                    effective_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        except Exception:
            pass

        return await self.extract_from_text(content, rel_path, effective_date=effective_date)

    # 그래프 추출 제외 경로 (스킬, 설정 파일 등)
    _EXCLUDE_DIRS = {"Skills", ".graph", ".obsidian", "assets"}
    _EXCLUDE_FILES = {"iam.yaml", "iam.yml", "README.md"}

    async def build_from_vault(self, vault_root: Path) -> dict[str, Any]:
        md_files = [
            f for f in vault_root.rglob("*.md")
            if not any(ex in f.relative_to(vault_root).parts for ex in self._EXCLUDE_DIRS)
            and f.name not in self._EXCLUDE_FILES
        ]
        logger.info("build_from_vault: %d files found (after exclusion)", len(md_files))

        self._store.clear()

        total_entities = 0
        total_rels = 0
        errors: list[str] = []
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _process(md_file: Path) -> tuple[int, int, str | None]:
            rel_path = "/" + md_file.relative_to(vault_root).as_posix()
            async with sem:
                try:
                    ents, rels = await self.extract_from_file(md_file, rel_path)
                    return len(ents), len(rels), None
                except Exception as exc:
                    logger.error("error on %s: %s", rel_path, exc)
                    return 0, 0, f"{rel_path}: {exc}"

        results = await asyncio.gather(*[_process(f) for f in md_files])
        for ne, nr, err in results:
            total_entities += ne
            total_rels += nr
            if err:
                errors.append(err)

        # ── 이미지 라벨링 → 그래프 엔티티 ─────────────────────────
        image_entities = 0
        assets_dir = vault_root / "assets"
        if assets_dir.exists():
            image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
            image_files = [
                f for f in assets_dir.rglob("*")
                if f.is_file() and f.suffix.lower() in image_exts
            ]
            if image_files:
                logger.info("Processing %d images for graph labeling", len(image_files))
                try:
                    from backend.ingestion.vlm_processor import get_image_processor
                    processor = get_image_processor()

                    async def _label_image(img_path: Path) -> Entity | None:
                        async with sem:
                            try:
                                result = await processor.analyze_image(img_path)
                                caption = result.get("caption", "") or img_path.stem
                                img_type = result.get("type", "diagram")
                                table_md = result.get("markdown_table", "")

                                rel_path = "/" + img_path.relative_to(vault_root).as_posix()
                                parent_doc = img_path.parent.name
                                source = [f"/assets/{parent_doc}/{img_path.name}"]

                                if img_type == "table" and table_md:
                                    # ── 표: 팩트 단위로 분해하여 저장 ──
                                    table_entity = Entity(
                                        id=f"tbl_{img_path.stem}",
                                        name=f"표: {parent_doc}" if parent_doc else f"표: {img_path.stem}",
                                        entity_type="table",
                                        properties={
                                            "image_path": rel_path,
                                            "raw_markdown": table_md[:800],
                                            "parent_document": parent_doc,
                                        },
                                        source_paths=source,
                                        mentions=1,
                                    )
                                    self._store.add_entity(table_entity)

                                    # LLM으로 표 팩트 분해
                                    try:
                                        facts = await self._decompose_table(table_md, parent_doc)
                                        for fact in facts:
                                            fact_entity = Entity(
                                                id=f"fact_{img_path.stem}_{fact['key'][:30].replace(' ','_')}",
                                                name=fact["key"],
                                                entity_type="fact",
                                                properties={
                                                    "value": fact["value"],
                                                    "context": fact.get("context", ""),
                                                    "parent_table": f"tbl_{img_path.stem}",
                                                    "parent_document": parent_doc,
                                                },
                                                source_paths=source,
                                                mentions=1,
                                            )
                                            self._store.add_entity(fact_entity)
                                            self._store.add_relationship(Relationship(
                                                source_id=f"tbl_{img_path.stem}",
                                                target_id=fact_entity.id,
                                                relation_type="contains",
                                                source_path=rel_path,
                                            ))
                                    except Exception as exc:
                                        logger.debug("Table decomposition failed: %s", exc)

                                    if parent_doc:
                                        self._store.add_relationship(Relationship(
                                            source_id=f"tbl_{img_path.stem}",
                                            target_id=parent_doc,
                                            relation_type="belongs_to",
                                            source_path=rel_path,
                                        ))
                                    return table_entity

                                else:
                                    # ── 이미지: 캡션으로 저장 ──
                                    entity = Entity(
                                        id=f"img_{img_path.stem}",
                                        name=caption[:80] if caption else img_path.stem,
                                        entity_type="image",
                                        properties={
                                            "image_path": rel_path,
                                            "caption": caption[:200],
                                            "parent_document": parent_doc,
                                        },
                                        source_paths=source,
                                        mentions=1,
                                    )
                                    self._store.add_entity(entity)
                                    if parent_doc:
                                        self._store.add_relationship(Relationship(
                                            source_id=entity.id,
                                            target_id=parent_doc,
                                            relation_type="belongs_to",
                                            source_path=rel_path,
                                        ))
                                    return entity

                            except Exception as exc:
                                logger.debug("Image labeling failed for %s: %s", img_path.name, exc)
                                return None

                    img_results = await asyncio.gather(*[_label_image(f) for f in image_files[:50]])
                    image_entities = sum(1 for r in img_results if r is not None)
                except Exception as exc:
                    logger.warning("Image labeling batch failed: %s", exc)

        communities = self._store.get_communities()
        self._store.save()

        return {
            "files": len(md_files),
            "entities": total_entities + image_entities,
            "relationships": total_rels,
            "image_entities": image_entities,
            "communities": len(communities),
            "errors": errors,
        }

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        text: str,
        existing_entities: list[str] | None = None,
    ) -> dict[str, Any]:
        if existing_entities:
            hint = ", ".join(existing_entities[:100])
            prompt = _EXTRACTION_PROMPT_WITH_HINTS.format(text=text, existing_entities=hint)
        else:
            prompt = _EXTRACTION_PROMPT.format(text=text)

        if self._use_wrapper:
            return await self._call_claude_wrapper(prompt)
        else:
            return await self._call_openai(prompt)

    async def _call_claude_wrapper(self, prompt: str) -> dict[str, Any]:
        client = self._get_http_client()
        payload = {
            "prompt": prompt,
            "systemPrompt": (
                "당신은 보험 약관 지식그래프 엔티티 추출 전문가입니다. "
                "보험 상품설계, 상담, 클레임, 언더라이팅에 필요한 정보를 정확하게 추출합니다. "
                "반드시 요청된 JSON 형식으로만 응답하세요."
            ),
            "allowedTools": [],
            "disallowedTools": ["Bash", "Edit", "Write", "WebSearch", "WebFetch"],
        }
        try:
            response = await client.post("/api/claude", json=payload)
            response.raise_for_status()
            data = response.json()
            return _parse_extraction_response(data.get("result", ""))
        except httpx.TimeoutException:
            logger.error("Claude wrapper timeout")
            return {"entities": [], "relationships": []}
        except Exception as exc:
            logger.error("Claude wrapper call failed: %s", exc)
            return {"entities": [], "relationships": []}

    async def _call_openai(self, prompt: str) -> dict[str, Any]:
        llm = self._get_llm()
        try:
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            raw = response.content if hasattr(response, "content") else str(response)
            return _parse_extraction_response(raw)
        except Exception as exc:
            logger.error("OpenAI call failed: %s", exc)
            return {"entities": [], "relationships": []}

    _TABLE_DECOMPOSE_PROMPT = (
        "다음 마크다운 표를 분석하여 개별 팩트(key-value)로 분해하세요.\n"
        "표의 헤더가 상단인지 좌측인지 자동 판별하세요.\n"
        "머지 셀이나 서브헤더가 있으면 컨텍스트를 포함하세요.\n\n"
        "표:\n{table}\n\n"
        "문서: {doc_name}\n\n"
        "JSON 배열로만 응답:\n"
        '[{{"key": "항목명 (구체적으로)", "value": "값", "context": "상위 구분/조건"}}]\n'
        "예: [{{"key": "1종 암진단금", "value": "5,000만원", "context": "무배당 건강보험"}}]"
    )

    async def _decompose_table(self, table_md: str, doc_name: str) -> list[dict[str, str]]:
        """마크다운 표를 LLM으로 분해하여 팩트 리스트를 반환합니다."""
        prompt = self._TABLE_DECOMPOSE_PROMPT.format(
            table=table_md[:600],
            doc_name=doc_name,
        )

        try:
            if self._use_wrapper:
                result = await self._call_claude_wrapper(prompt)
            else:
                llm = self._get_llm()
                response = await llm.ainvoke([{"role": "user", "content": prompt}])
                raw = response.content if hasattr(response, "content") else str(response)
                # JSON 배열 파싱
                import re
                json_match = re.search(r'\[.*\]', raw, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    if isinstance(result, list):
                        return result
                return []
        except Exception as exc:
            logger.debug("Table decompose LLM failed: %s", exc)
            return []

    def _build_graph_objects(
        self,
        extraction: dict[str, Any],
        source_path: str,
        page_range: tuple[int | None, int | None] = (None, None),
        effective_date: str | None = None,
    ) -> tuple[list[Entity], list[Relationship]]:
        entities: list[Entity] = []
        relationships: list[Relationship] = []
        name_to_id: dict[str, str] = {}

        source_doc_name = _extract_source_doc_name(source_path)

        for e_dict in extraction.get("entities", []):
            name = str(e_dict.get("name", "")).strip()
            if not name:
                continue
            entity_id = _slugify(name)
            entity_type = str(e_dict.get("type", "concept")).lower()
            description = str(e_dict.get("description", ""))

            # 보험 도메인 프로퍼티 수집
            props: dict[str, Any] = {}
            if description:
                props["description"] = description
            # 출처 문서명 항상 기록
            props["source_document"] = source_doc_name

            # 페이지 범위 기록
            if page_range[0] is not None:
                props["page_start"] = page_range[0]
            if page_range[1] is not None:
                props["page_end"] = page_range[1]

            # 시행일 기록 (문서 버전 관리)
            if effective_date:
                props["effective_date"] = effective_date

            # LLM이 추출한 구조화된 프로퍼티 병합
            raw_props = e_dict.get("properties", {})
            if isinstance(raw_props, dict):
                for key in _ALLOWED_PROPERTIES:
                    val = raw_props.get(key)
                    if val:
                        props[key] = val

            entity = Entity(
                id=entity_id,
                name=name,
                entity_type=entity_type,
                properties=props,
                source_paths=[source_path],
                mentions=1,
            )
            entities.append(entity)
            name_to_id[name.lower()] = entity_id

        for r_dict in extraction.get("relationships", []):
            src_name = str(r_dict.get("source", "")).strip()
            tgt_name = str(r_dict.get("target", "")).strip()
            rel_type = str(r_dict.get("type", "references")).strip()

            if not src_name or not tgt_name:
                continue

            src_id = name_to_id.get(src_name.lower(), _slugify(src_name))
            tgt_id = name_to_id.get(tgt_name.lower(), _slugify(tgt_name))

            rel = Relationship(
                source_id=src_id,
                target_id=tgt_id,
                relation_type=rel_type,
                properties={
                    "description": str(r_dict.get("description", "")),
                    "source_document": source_doc_name,
                },
                source_path=source_path,
                weight=1.0,
            )
            relationships.append(rel)

        return entities, relationships


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_extractor: GraphExtractor | None = None


def get_graph_extractor() -> GraphExtractor:
    global _extractor
    if _extractor is None:
        from backend.graph.store import GraphStore
        _store = GraphStore()
        _extractor = GraphExtractor(graph_store=_store)
    return _extractor
