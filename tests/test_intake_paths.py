"""Tests for intake agent path validation.

Covers:
- _has_build_files() detection
- _fix_component_paths() correcting source_dir when it points to a
  source code subdirectory instead of the component root
"""

from pathlib import Path

import pytest

from autopoc.agents.intake import _fix_component_paths, _has_build_files


class TestHasBuildFiles:
    """Test that _has_build_files correctly identifies component roots."""

    def test_python_setup_py(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").touch()
        assert _has_build_files(tmp_path) is True

    def test_python_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        assert _has_build_files(tmp_path) is True

    def test_python_requirements_txt(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").touch()
        assert _has_build_files(tmp_path) is True

    def test_node_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        assert _has_build_files(tmp_path) is True

    def test_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        assert _has_build_files(tmp_path) is True

    def test_rust_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert _has_build_files(tmp_path) is True

    def test_dockerfile(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").touch()
        assert _has_build_files(tmp_path) is True

    def test_dockerfile_ubi(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile.ubi").touch()
        assert _has_build_files(tmp_path) is True

    def test_makefile(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").touch()
        assert _has_build_files(tmp_path) is True

    def test_empty_dir_has_no_build_files(self, tmp_path: Path) -> None:
        assert _has_build_files(tmp_path) is False

    def test_python_source_dir_only(self, tmp_path: Path) -> None:
        """A Python package directory with only __init__.py is not a component root."""
        (tmp_path / "__init__.py").touch()
        (tmp_path / "main.py").touch()
        assert _has_build_files(tmp_path) is False


class TestFixComponentPaths:
    """Test that _fix_component_paths corrects source_dir when the LLM
    confuses a source code subdirectory with the component root."""

    @pytest.mark.asyncio
    async def test_source_subdir_without_build_files_corrected_to_root(
        self, tmp_path: Path
    ) -> None:
        """When source_dir points to a subdir with no build files but the
        repo root has build files, correct to '.'."""
        # Simulate: repo root has pyproject.toml, subdir is Python package
        (tmp_path / "pyproject.toml").write_text("[project]\nname='mylib'\n")
        pkg_dir = tmp_path / "mylib"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "core.py").touch()

        components = [{"name": "mylib", "source_dir": "mylib", "language": "python"}]

        # LLM mock not needed — the correction is deterministic (no LLM call)
        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()

        result = await _fix_component_paths(components, tmp_path, mock_llm)

        assert len(result) == 1
        assert result[0]["source_dir"] == "."
        # LLM should NOT have been called (deterministic fix, not LLM correction)
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_dir_root_unchanged(self, tmp_path: Path) -> None:
        """source_dir='.' should pass through unchanged."""
        (tmp_path / "setup.py").touch()

        components = [{"name": "myapp", "source_dir": ".", "language": "python"}]

        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()

        result = await _fix_component_paths(components, tmp_path, mock_llm)

        assert len(result) == 1
        assert result[0]["source_dir"] == "."

    @pytest.mark.asyncio
    async def test_monorepo_subdir_with_build_files_kept(self, tmp_path: Path) -> None:
        """In a monorepo, subdirs with their own build files should keep
        their source_dir (not be corrected to '.')."""
        # Repo root has a top-level package.json (monorepo root)
        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')

        # Subdir has its own package.json (monorepo component)
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text('{"name": "frontend"}')
        (frontend / "src").mkdir()

        components = [{"name": "frontend", "source_dir": "frontend", "language": "typescript"}]

        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()

        result = await _fix_component_paths(components, tmp_path, mock_llm)

        assert len(result) == 1
        assert result[0]["source_dir"] == "frontend"

    @pytest.mark.asyncio
    async def test_nonexistent_dir_triggers_llm_correction(self, tmp_path: Path) -> None:
        """When source_dir doesn't exist at all, LLM is asked to correct it."""
        (tmp_path / "setup.py").touch()
        (tmp_path / "src").mkdir()

        components = [{"name": "myapp", "source_dir": "nonexistent", "language": "python"}]

        from unittest.mock import AsyncMock, MagicMock

        mock_response = MagicMock()
        mock_response.content = "."
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response

        result = await _fix_component_paths(components, tmp_path, mock_llm)

        assert len(result) == 1
        assert result[0]["source_dir"] == "."
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_llmsearchindex_pattern(self, tmp_path: Path) -> None:
        """Reproduces the llmsearchindex failure: Python package dir mistaken
        for component root. Repo root has setup.py, subdir is just source code."""
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()")
        (tmp_path / "requirements.txt").write_text("numpy\n")

        pkg_dir = tmp_path / "llmsearchindex"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "index.py").touch()

        components = [
            {"name": "llmsearchindex", "source_dir": "llmsearchindex", "language": "python"}
        ]

        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()

        result = await _fix_component_paths(components, tmp_path, mock_llm)

        assert len(result) == 1
        assert result[0]["source_dir"] == ".", (
            "source_dir should be corrected to '.' because llmsearchindex/ "
            "has no build files but the repo root has setup.py"
        )
