from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_required_scaffold_paths_exist() -> None:
    required = [
        "app.py",
        "requirements.txt",
        "environment.yml",
        "Dockerfile",
        "compose.yaml",
        "templates/index.html",
        "static/styles.css",
        "static/app.js",
        "docs/PRD.md",
        "docs/SYSTEM_DESIGN.md",
        "docs/API.md",
        "docs/GIT_WORKFLOW.md",
        "docs/TEAM_ROSTER.md",
    ]

    missing = [path for path in required if not (ROOT / path).is_file()]

    assert missing == []


def test_five_assignment_and_prompt_packages_exist() -> None:
    assignments = sorted((ROOT / "docs" / "assignments").glob("*.md"))
    prompts = sorted((ROOT / "prompts").glob("*.md"))

    assert len(assignments) == 5
    assert len(prompts) == 5


def test_each_prompt_is_a_self_contained_role_contract() -> None:
    required_sections = {
        "## 角色定义",
        "## 前置阅读",
        "## 唯一可写路径与禁止越界项",
        "## 固定接口",
        "## 分步工作",
        "## 测试命令与验证",
        "## 提交粒度",
        "## 验收条件",
        "## 契约冲突处理",
    }

    for prompt in sorted((ROOT / "prompts").glob("*.md")):
        content = prompt.read_text(encoding="utf-8")
        missing = sorted(section for section in required_sections if section not in content)

        assert missing == [], f"{prompt.name} 缺少章节: {missing}"
