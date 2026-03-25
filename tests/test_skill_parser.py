"""Tests for backend.agents.skill_parser (SkillRegistry)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from langchain_core.tools import StructuredTool

from backend.agents.skill_parser import SkillRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def skills_vault(tmp_path: Path) -> Path:
    """Minimal vault with a single skill file and a non-skill file."""
    skills_dir = tmp_path / "Skills"
    skills_dir.mkdir()

    # Primary skill file
    skill_md = textwrap.dedent("""\
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
        owner: admin01
        ---

        # 보험료 산출 (Calculate Insurance Premium)

        보험료 산출 스킬은 레거시 코어 시스템의 보험료 계산 API를 호출합니다.
    """)
    (skills_dir / "calculate-insurance-premium.md").write_text(skill_md, encoding="utf-8")

    # Second skill – GET method, no depends_on
    skill2_md = textwrap.dedent("""\
        ---
        type: skill
        skill_name: get-product-spec
        description: "상품 사양서 조회"
        endpoint: "http://legacy-core:8080/api/products"
        method: GET
        depends_on: []
        params:
          product_code:
            type: string
            required: true
        ---

        상품 사양서를 조회합니다.
    """)
    (skills_dir / "get-product-spec.md").write_text(skill2_md, encoding="utf-8")

    # Non-skill file – should be ignored
    non_skill_md = textwrap.dedent("""\
        ---
        type: note
        title: General Note
        ---

        This is just a note.
    """)
    (skills_dir / "general-note.md").write_text(non_skill_md, encoding="utf-8")

    return tmp_path


@pytest.fixture()
def registry(skills_vault: Path) -> SkillRegistry:
    """Return a fully-loaded SkillRegistry for the skills_vault."""
    reg = SkillRegistry(skills_dir=skills_vault / "Skills" if (skills_vault / "Skills").exists() else skills_vault)
    reg.load_all()
    return reg


# ---------------------------------------------------------------------------
# test_load_skill_from_md
# ---------------------------------------------------------------------------


def test_load_skill_metadata_name(registry: SkillRegistry) -> None:
    """Skill name is read from the 'skill_name' frontmatter field."""
    skill = registry.get_skill("calculate-insurance-premium")
    assert skill is not None
    assert skill["name"] == "calculate-insurance-premium"


def test_load_skill_metadata_endpoint(registry: SkillRegistry) -> None:
    """Endpoint URL is parsed from frontmatter."""
    skill = registry.get_skill("calculate-insurance-premium")
    assert skill["endpoint"] == "http://legacy-core:8080/api/premium/calculate"


def test_load_skill_metadata_method(registry: SkillRegistry) -> None:
    """HTTP method is read from frontmatter and uppercased."""
    skill = registry.get_skill("calculate-insurance-premium")
    assert skill["method"] == "POST"


def test_load_skill_metadata_description(registry: SkillRegistry) -> None:
    """Description field is captured from frontmatter."""
    skill = registry.get_skill("calculate-insurance-premium")
    assert "보험료" in skill["description"]


def test_load_skill_metadata_params_schema(registry: SkillRegistry) -> None:
    """params dict from frontmatter is stored in the skill record."""
    skill = registry.get_skill("calculate-insurance-premium")
    assert "product_code" in skill["params_schema"]
    assert "insured_age" in skill["params_schema"]


def test_non_skill_files_ignored(registry: SkillRegistry) -> None:
    """Markdown files with type != 'skill' are not loaded into the registry."""
    # general-note.md has type:note – should be absent
    names = [s["name"] for s in registry.list_skills()]
    assert "general-note" not in names
    assert "General Note" not in names


# ---------------------------------------------------------------------------
# test_skill_registry_list
# ---------------------------------------------------------------------------


def test_skill_registry_list_returns_all_skills(registry: SkillRegistry) -> None:
    """list_skills returns one entry per loaded skill."""
    skills = registry.list_skills()
    assert len(skills) == 2


def test_skill_registry_list_contains_expected_names(registry: SkillRegistry) -> None:
    """Both skill names appear in the listing."""
    names = {s["name"] for s in registry.list_skills()}
    assert "calculate-insurance-premium" in names
    assert "get-product-spec" in names


def test_skill_registry_list_entries_are_dicts(registry: SkillRegistry) -> None:
    """Each entry returned by list_skills is a dict."""
    for skill in registry.list_skills():
        assert isinstance(skill, dict)


def test_skill_registry_empty_when_no_skills_dir(tmp_path: Path) -> None:
    """SkillRegistry silently handles a missing Skills directory."""
    reg = SkillRegistry(skills_dir=tmp_path)
    reg.load_all()

    assert reg.list_skills() == []


# ---------------------------------------------------------------------------
# test_depends_on_parsed
# ---------------------------------------------------------------------------


def test_depends_on_parsed_list(registry: SkillRegistry) -> None:
    """depends_on is a list of skill name strings."""
    skill = registry.get_skill("calculate-insurance-premium")
    deps = skill["depends_on"]

    assert isinstance(deps, list)
    assert "validate-customer-info" in deps
    assert "get-product-spec" in deps


def test_depends_on_order_preserved(registry: SkillRegistry) -> None:
    """depends_on preserves the declaration order from frontmatter."""
    skill = registry.get_skill("calculate-insurance-premium")
    deps = skill["depends_on"]

    assert deps[0] == "validate-customer-info"
    assert deps[1] == "get-product-spec"


def test_depends_on_empty_list(registry: SkillRegistry) -> None:
    """A skill with no dependencies stores an empty list."""
    skill = registry.get_skill("get-product-spec")
    assert skill["depends_on"] == []


# ---------------------------------------------------------------------------
# test_tool_creation
# ---------------------------------------------------------------------------


def test_tool_creation_returns_structured_tool(registry: SkillRegistry) -> None:
    """get_tool returns a StructuredTool instance."""
    tool = registry.get_tool("calculate-insurance-premium")
    assert isinstance(tool, StructuredTool)


def test_tool_creation_correct_name(registry: SkillRegistry) -> None:
    """StructuredTool.name matches the skill_name from frontmatter."""
    tool = registry.get_tool("calculate-insurance-premium")
    assert tool.name == "calculate-insurance-premium"


def test_tool_creation_correct_description(registry: SkillRegistry) -> None:
    """StructuredTool.description contains the description from frontmatter."""
    tool = registry.get_tool("calculate-insurance-premium")
    assert "보험료" in tool.description


def test_tool_creation_for_get_skill(registry: SkillRegistry) -> None:
    """A GET-method skill also gets a StructuredTool created."""
    tool = registry.get_tool("get-product-spec")
    assert isinstance(tool, StructuredTool)
    assert tool.name == "get-product-spec"


def test_tool_none_for_unknown_skill(registry: SkillRegistry) -> None:
    """get_tool returns None for an unregistered skill name."""
    assert registry.get_tool("nonexistent-skill") is None


def test_get_skill_none_for_unknown(registry: SkillRegistry) -> None:
    """get_skill returns None for an unregistered name."""
    assert registry.get_skill("unknown") is None


def test_source_path_recorded(registry: SkillRegistry, skills_vault: Path) -> None:
    """The 'source' field records the absolute path to the skill file."""
    skill = registry.get_skill("calculate-insurance-premium")
    expected = str(skills_vault / "Skills" / "calculate-insurance-premium.md")
    assert skill["source"] == expected
