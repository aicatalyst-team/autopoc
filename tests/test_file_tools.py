"""Tests for autopoc.tools.file_tools module."""

from pathlib import Path

import pytest

from autopoc.tools.file_tools import list_files, read_file, search_files, write_file


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Create a sample file tree for testing."""
    # Create directory structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("import os\nprint('hello')\n")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_hello():\n    assert True\n")
    (tmp_path / "README.md").write_text("# My Project\nA sample project.\n")
    (tmp_path / "requirements.txt").write_text("flask==3.0\nrequests\n")
    # Hidden dir (should be skipped)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")
    return tmp_path


class TestListFiles:
    def test_lists_all_files(self, sample_tree: Path) -> None:
        result = list_files.invoke({"path": str(sample_tree)})
        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "README.md" in result
        assert "requirements.txt" in result
        assert "tests/test_main.py" in result

    def test_excludes_hidden_dirs(self, sample_tree: Path) -> None:
        result = list_files.invoke({"path": str(sample_tree)})
        assert ".git" not in result
        assert "config" not in result

    def test_glob_pattern_filter(self, sample_tree: Path) -> None:
        result = list_files.invoke({"path": str(sample_tree), "pattern": "**/*.py"})
        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "README.md" not in result

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        result = list_files.invoke({"path": str(tmp_path / "nope")})
        assert "Error" in result or "not a directory" in result

    def test_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = list_files.invoke({"path": str(empty)})
        assert "No files found" in result


class TestReadFile:
    def test_reads_file_contents(self, sample_tree: Path) -> None:
        result = read_file.invoke({"path": str(sample_tree / "src" / "main.py")})
        assert "import os" in result
        assert "print('hello')" in result

    def test_nonexistent_file(self, sample_tree: Path) -> None:
        result = read_file.invoke({"path": str(sample_tree / "nope.txt")})
        assert "Error" in result or "not a file" in result

    def test_truncates_large_file(self, tmp_path: Path) -> None:
        large = tmp_path / "large.txt"
        large.write_text("x" * 100_000)
        result = read_file.invoke({"path": str(large)})
        assert "truncated" in result


class TestWriteFile:
    def test_writes_new_file(self, tmp_path: Path) -> None:
        target = str(tmp_path / "output.txt")
        result = write_file.invoke({"path": target, "content": "hello world"})
        assert "Successfully wrote" in result
        assert Path(target).read_text() == "hello world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = str(tmp_path / "a" / "b" / "c" / "file.txt")
        result = write_file.invoke({"path": target, "content": "nested"})
        assert "Successfully wrote" in result
        assert Path(target).read_text() == "nested"

    def test_overwrites_existing_file(self, sample_tree: Path) -> None:
        target = str(sample_tree / "README.md")
        write_file.invoke({"path": target, "content": "new content"})
        assert Path(target).read_text() == "new content"


class TestSearchFiles:
    def test_finds_matches(self, sample_tree: Path) -> None:
        result = search_files.invoke({"path": str(sample_tree), "pattern": "import"})
        assert "src/main.py:1:" in result
        assert "import os" in result

    def test_no_matches(self, sample_tree: Path) -> None:
        result = search_files.invoke(
            {"path": str(sample_tree), "pattern": "nonexistent_string_xyz"}
        )
        assert "No matches found" in result

    def test_regex_pattern(self, sample_tree: Path) -> None:
        result = search_files.invoke({"path": str(sample_tree), "pattern": r"def \w+\("})
        assert "utils.py" in result
        assert "helper" in result

    def test_file_glob_filter(self, sample_tree: Path) -> None:
        result = search_files.invoke(
            {"path": str(sample_tree), "pattern": "assert", "file_glob": "**/*.py"}
        )
        assert "test_main.py" in result
        # README.md should not be searched
        assert "README" not in result

    def test_invalid_regex(self, sample_tree: Path) -> None:
        result = search_files.invoke({"path": str(sample_tree), "pattern": "[invalid"})
        assert "Error" in result or "invalid regex" in result

    def test_skips_hidden_dirs(self, sample_tree: Path) -> None:
        result = search_files.invoke({"path": str(sample_tree), "pattern": "core"})
        # .git/config has [core] but should be skipped
        assert ".git" not in result
