"""Skill loader for Markdown-based skills.

Skills are defined in Markdown files with YAML frontmatter:

```markdown
---
name: code-review
description: Review code for issues
allowedTools: [Read, Grep]
---

Please review the following code...
```
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import yaml

from ..core.types import SkillDefinition


class SkillLoadError(Exception):
    """Error loading a skill."""

    pass


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from Markdown content.

    Args:
        content: Full Markdown content with optional frontmatter

    Returns:
        Tuple of (frontmatter_dict, markdown_content)
    """
    # Match frontmatter between --- delimiters
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    markdown_content = content[match.end() :]

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        raise SkillLoadError(f"Invalid YAML frontmatter: {e}")

    return frontmatter, markdown_content


def load_skill_from_file(file_path: Path) -> SkillDefinition:
    """Load a skill from a Markdown file.

    Args:
        file_path: Path to the .md file

    Returns:
        SkillDefinition
    """
    if not file_path.exists():
        raise SkillLoadError(f"Skill file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    frontmatter, markdown = parse_frontmatter(content)

    # Extract name from frontmatter - required for plugin skills
    name = frontmatter.get("name")
    if not name:
        raise SkillLoadError(f"Skill file {file_path} missing required 'name' field in frontmatter")

    # Build skill definition
    skill = SkillDefinition(
        name=name,
        description=frontmatter.get("description", ""),
        aliases=frontmatter.get("aliases", []),
        when_to_use=frontmatter.get("whenToUse") or frontmatter.get("when_to_use"),
        argument_hint=frontmatter.get("argumentHint") or frontmatter.get("argument_hint"),
        allowed_tools=frontmatter.get("allowedTools") or frontmatter.get("allowed_tools", []),
        model=frontmatter.get("model"),
        content=markdown.strip(),
    )

    return skill


class SkillLoader:
    """Loader for plugin skills.

    Loads skills from a directory of Markdown files.
    """

    def __init__(self, skills_path: Path):
        self.skills_path = Path(skills_path)
        self._skills: dict[str, SkillDefinition] = {}

    def load_all(self) -> list[SkillDefinition]:
        """Load all skills from the directory.

        Returns:
            List of loaded skills
        """
        if not self.skills_path.exists():
            return []

        skills = []

        # Load individual .md files
        for md_file in self.skills_path.glob("*.md"):
            try:
                skill = load_skill_from_file(md_file)
                self._skills[skill.name] = skill
                skills.append(skill)
            except SkillLoadError as e:
                print(f"Warning: Failed to load skill {md_file}: {e}")

        # Load skills from subdirectories (each dir is a skill with SKILL.md)
        for subdir in self.skills_path.iterdir():
            if subdir.is_dir():
                skill_md = subdir / "SKILL.md"
                if skill_md.exists():
                    try:
                        skill = load_skill_from_file(skill_md)
                        self._skills[skill.name] = skill
                        skills.append(skill)
                    except SkillLoadError as e:
                        print(f"Warning: Failed to load skill {subdir}: {e}")

        return skills

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Get a loaded skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """List names of all loaded skills."""
        return list(self._skills.keys())
