"""Tests for language-specific compilation guidance."""

from pilotcode.orchestration.language_guide import (
    detect_languages_from_files,
    detect_languages_from_text,
    get_compile_hint,
    get_compile_hints_for_files,
    build_verification_section,
)


class TestLanguageDetection:
    def test_detect_from_py(self):
        assert detect_languages_from_files(["src/main.py"]) == ["python"]

    def test_detect_from_cpp(self):
        assert detect_languages_from_files(["src/main.cpp"]) == ["cpp"]

    def test_detect_from_c(self):
        assert detect_languages_from_files(["src/main.c"]) == ["c"]

    def test_detect_multiple(self):
        langs = detect_languages_from_files(["a.py", "b.cpp", "c.rs"])
        assert langs == ["cpp", "python", "rust"]

    def test_detect_from_unknown_ext(self):
        assert detect_languages_from_files(["readme.md"]) == []

    def test_detect_from_text_python(self):
        assert "python" in detect_languages_from_text("write a python script")
        assert "python" in detect_languages_from_text("use pytest for testing")

    def test_detect_from_text_cpp(self):
        assert "cpp" in detect_languages_from_text("fix the cpp file")
        assert "cpp" in detect_languages_from_text("edit the .cpp file")

    def test_detect_from_text_rust(self):
        assert "rust" in detect_languages_from_text("cargo build the project")


class TestCompileHints:
    def test_compile_hint_python(self):
        hint = get_compile_hint("test.py")
        assert hint is not None
        assert "py_compile" in hint

    def test_compile_hint_cpp(self):
        hint = get_compile_hint("test.cpp")
        assert hint is not None
        assert "g++" in hint

    def test_compile_hint_c(self):
        hint = get_compile_hint("test.c")
        assert hint is not None
        assert "gcc" in hint

    def test_compile_hint_unsupported(self):
        assert get_compile_hint("test.md") is None

    def test_hints_for_files(self):
        hints = get_compile_hints_for_files(["a.py", "b.cpp"])
        assert "py_compile" in hints
        assert "g++" in hints

    def test_hints_for_empty(self):
        assert get_compile_hints_for_files([]) == ""

    def test_hints_for_unknown(self):
        assert get_compile_hints_for_files(["readme.md"]) == ""


class TestVerificationSection:
    def test_build_verification_section_py(self):
        section = build_verification_section(["test.py"], "write a python function")
        assert "py_compile" in section or "Python" in section

    def test_build_verification_section_cpp(self):
        section = build_verification_section(["main.cpp"], "fix c++ bug")
        assert "C++" in section

    def test_build_verification_section_unknown(self):
        assert build_verification_section(["readme.md"], "") == ""

    def test_build_verification_section_mixed(self):
        section = build_verification_section(["a.py", "b.cpp", "c.c"], "implement feature")
        assert "Python" in section
        assert "C++" in section
        assert "C " in section or "C:" in section
