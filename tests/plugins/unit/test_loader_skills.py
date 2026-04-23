"""Unit tests for skill loader."""

import pytest

try:
    from pilotcode.plugins.loader.skills import (
        parse_frontmatter,
        load_skill_from_file,
        SkillLoader,
        SkillLoadError,
    )

    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.plugin,
    pytest.mark.plugin_unit,
    pytest.mark.unit,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


class TestParseFrontmatter:
    """Test frontmatter parsing."""

    def test_parse_with_frontmatter(self):
        """Test parsing content with frontmatter."""
        content = """---
name: test-skill
description: A test skill
allowedTools: [Read, Grep]
---

This is the skill content.
More content here.
"""
        frontmatter, markdown = parse_frontmatter(content)

        assert frontmatter["name"] == "test-skill"
        assert frontmatter["description"] == "A test skill"
        assert frontmatter["allowedTools"] == ["Read", "Grep"]
        assert "This is the skill content" in markdown

    def test_parse_without_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "Just markdown content\nNo frontmatter here."
        frontmatter, markdown = parse_frontmatter(content)

        assert frontmatter == {}
        assert markdown == content

    def test_parse_empty_frontmatter(self):
        """Test parsing with empty frontmatter."""
        content = """---
---

Content only.
"""
        frontmatter, markdown = parse_frontmatter(content)

        assert frontmatter == {}
        assert "Content only" in markdown

    def test_parse_multiline_description(self):
        """Test parsing multiline description."""
        content = """---
name: test
description: |
  This is a multiline
  description that spans
  multiple lines.
---

Content.
"""
        frontmatter, markdown = parse_frontmatter(content)

        assert "multiline" in frontmatter["description"]

    def test_parse_invalid_yaml(self):
        """Test handling of invalid YAML."""
        content = """---
name: test
invalid: yaml: here: 
---

Content.
"""
        with pytest.raises(SkillLoadError):
            parse_frontmatter(content)


class TestLoadSkillFromFile:
    """Test loading skills from files."""

    def test_load_valid_skill(self, tmp_path):
        """Test loading a valid skill file."""
        skill_file = tmp_path / "test-skill.md"
        skill_file.write_text("""---
name: my-skill
description: My test skill
aliases: [ms, my]
allowedTools: [Read, Bash]
---

Do something useful.
""")

        skill = load_skill_from_file(skill_file)

        assert skill.name == "my-skill"
        assert skill.description == "My test skill"
        assert skill.aliases == ["ms", "my"]
        assert skill.allowed_tools == ["Read", "Bash"]
        assert "Do something useful" in skill.content

    def test_load_skill_without_name_raises_error(self, tmp_path):
        """Test that error is raised when name not in frontmatter."""
        skill_file = tmp_path / "filename-skill.md"
        skill_file.write_text("""---
description: Uses filename
---

Content here.
""")

        # Should raise error because name is required
        with pytest.raises(SkillLoadError):
            load_skill_from_file(skill_file)

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading file that doesn't exist."""
        with pytest.raises(SkillLoadError):
            load_skill_from_file(tmp_path / "nonexistent.md")

    def test_load_skill_complex_content(self, tmp_path):
        """Test loading skill with complex markdown content."""
        skill_file = tmp_path / "complex.md"
        skill_file.write_text("""---
name: complex-skill
description: A complex skill
---

# Header

Some **bold** and *italic* text.

```python
print("code block")
```

- List item 1
- List item 2
""")

        skill = load_skill_from_file(skill_file)

        assert "# Header" in skill.content
        assert "```python" in skill.content


class TestSkillLoader:
    """Test SkillLoader class."""

    def test_load_all_from_directory(self, tmp_path):
        """Test loading all skills from directory."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create multiple skill files
        (skills_dir / "skill1.md").write_text("""---
name: skill-one
description: First skill
---
Content 1
""")
        (skills_dir / "skill2.md").write_text("""---
name: skill-two
description: Second skill
---
Content 2
""")

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert len(skills) == 2
        names = [s.name for s in skills]
        assert "skill-one" in names
        assert "skill-two" in names

    def test_load_from_subdirectories(self, tmp_path):
        """Test loading skills from subdirectories."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create SKILL.md in subdirectory
        subdir = skills_dir / "complex-skill"
        subdir.mkdir()
        (subdir / "SKILL.md").write_text("""---
name: complex
description: Complex skill
---
Content
""")

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert len(skills) == 1
        assert skills[0].name == "complex"

    def test_load_empty_directory(self, tmp_path):
        """Test loading from empty directory."""
        skills_dir = tmp_path / "empty"
        skills_dir.mkdir()

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert skills == []

    def test_load_nonexistent_directory(self, tmp_path):
        """Test loading from non-existent directory."""
        loader = SkillLoader(tmp_path / "nonexistent")
        skills = loader.load_all()

        assert skills == []

    def test_get_skill(self, tmp_path):
        """Test getting skill by name."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "test.md").write_text("""---
name: test-skill
description: Test
---
Content
""")

        loader = SkillLoader(skills_dir)
        loader.load_all()

        skill = loader.get_skill("test-skill")
        assert skill is not None
        assert skill.name == "test-skill"

        # Non-existent skill
        assert loader.get_skill("nonexistent") is None

    def test_list_skills(self, tmp_path):
        """Test listing loaded skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "skill1.md").write_text("---\nname: s1\n---\n")
        (skills_dir / "skill2.md").write_text("---\nname: s2\n---\n")

        loader = SkillLoader(skills_dir)
        loader.load_all()

        names = loader.list_skills()
        assert sorted(names) == ["s1", "s2"]

    def test_skip_invalid_skills(self, tmp_path, capsys):
        """Test that invalid skills are skipped with warning."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Valid skill
        (skills_dir / "valid.md").write_text("---\nname: valid\n---\nContent")

        # Invalid skill (no name, no frontmatter)
        (skills_dir / "invalid.md").write_text("Just content\nNo frontmatter")

        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        # Should load the valid one
        assert len(skills) == 1
        assert skills[0].name == "valid"
