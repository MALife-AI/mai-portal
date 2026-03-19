"""Shared pytest fixtures for the malife-lake test suite."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from backend.core.iam import IAMEngine


# ---------------------------------------------------------------------------
# IAM YAML content mirroring the real vault/iam.yaml
# ---------------------------------------------------------------------------

_IAM_YAML = {
    "roles": {
        "admin": {
            "description": "시스템 관리자",
            "allowed_paths": {
                "read": ["/Public/**", "/Private/**", "/Skills/**"],
                "write": ["/Public/**", "/Private/**", "/Skills/**"],
            },
        },
        "underwriter": {
            "description": "언더라이터 (심사역)",
            "allowed_paths": {
                "read": ["/Public/**", "/Public/underwriting/**", "/Skills/**"],
                "write": ["/Public/underwriting/**"],
            },
        },
        "analyst": {
            "description": "데이터 분석가",
            "allowed_paths": {
                "read": ["/Public/**", "/Skills/**"],
                "write": ["/Public/reports/**"],
            },
        },
        "viewer": {
            "description": "일반 조회자",
            "allowed_paths": {
                "read": ["/Public/**"],
                "write": [],
            },
        },
    },
    "users": [
        {"user_id": "admin01", "roles": ["admin"], "display_name": "시스템 관리자"},
        {"user_id": "uw001", "roles": ["underwriter"], "display_name": "김심사"},
        {"user_id": "analyst01", "roles": ["analyst"], "display_name": "이분석"},
        {"user_id": "user01", "roles": ["viewer"], "display_name": "박조회"},
    ],
}

# ---------------------------------------------------------------------------
# Sample skill markdown (mirrors vault/Skills/calculate-insurance-premium.md)
# ---------------------------------------------------------------------------

SAMPLE_SKILL_MD = textwrap.dedent("""\
    ---
    type: skill
    skill_name: calculate-insurance-premium
    description: "보험료 산출 스킬 - 상품코드와 피보험자 정보를 기반으로 보험료를 계산합니다."
    endpoint: "http://legacy-core:8080/api/premium/calculate"
    method: POST
    depends_on:
      - validate-customer-info
      - get-product-spec
    params:
      product_code:
        type: string
        required: true
      insured_age:
        type: integer
        required: true
      coverage_amount:
        type: number
        required: true
      payment_period:
        type: integer
        required: true
    owner: admin01
    created_at: "2026-01-15T09:00:00Z"
    updated_at: "2026-03-10T14:30:00Z"
    ---

    # 보험료 산출 (Calculate Insurance Premium)

    ## 개요
    보험료 산출 스킬은 레거시 코어 시스템의 보험료 계산 API를 호출합니다.
""")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_vault(tmp_path: Path) -> Path:
    """Create a minimal vault directory tree with iam.yaml and sample files."""
    # --- iam.yaml ---
    iam_file = tmp_path / "iam.yaml"
    with open(iam_file, "w", encoding="utf-8") as fh:
        yaml.dump(_IAM_YAML, fh, allow_unicode=True, default_flow_style=False)

    # --- Public content ---
    public_dir = tmp_path / "Public"
    public_dir.mkdir()
    (public_dir / "readme.md").write_text("# Public Readme\nHello world.\n", encoding="utf-8")

    underwriting_dir = public_dir / "underwriting"
    underwriting_dir.mkdir()
    (underwriting_dir / "guide.md").write_text("# Underwriting Guide\n", encoding="utf-8")

    reports_dir = public_dir / "reports"
    reports_dir.mkdir()
    (reports_dir / "q1.md").write_text("# Q1 Report\n", encoding="utf-8")

    # --- Private content for user01 and admin01 ---
    for uid in ("user01", "admin01", "uw001"):
        priv_dir = tmp_path / "Private" / uid
        priv_dir.mkdir(parents=True)
        (priv_dir / "notes.md").write_text(f"# {uid} private notes\n", encoding="utf-8")

    # --- Skills directory ---
    skills_dir = tmp_path / "Skills"
    skills_dir.mkdir()
    skill_file = skills_dir / "calculate-insurance-premium.md"
    skill_file.write_text(SAMPLE_SKILL_MD, encoding="utf-8")

    return tmp_path


@pytest.fixture()
def iam_engine(tmp_vault: Path) -> IAMEngine:
    """Return an IAMEngine loaded from the tmp_vault iam.yaml."""
    return IAMEngine(tmp_vault / "iam.yaml")


@pytest.fixture()
def sample_skill_md() -> str:
    """Return the raw markdown string for the sample skill."""
    return SAMPLE_SKILL_MD
