"""Tests for Dockerfile extraction from LLM responses.

Covers _extract_dockerfile_from_response and _fixup_dockerfile to prevent
regressions in handling various LLM output formats (Claude, Qwen, etc.).
"""

from pathlib import Path

import pytest

from autopoc.agents.containerize import (
    _extract_dockerfile_from_response,
    _fixup_dockerfile,
    _uses_minimal_base,
)


class TestExtractDockerfileFromResponse:
    """Tests for extracting Dockerfile content from raw LLM output."""

    def test_markdown_dockerfile_block(self):
        """Standard ```dockerfile ... ``` code block."""
        raw = (
            "Here is the Dockerfile:\n"
            "```dockerfile\n"
            "FROM registry.access.redhat.com/ubi9/python-312\n"
            "WORKDIR /app\n"
            "COPY . .\n"
            "RUN pip install .\n"
            "USER 1001\n"
            "```\n"
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM registry.access.redhat.com/ubi9/python-312")
        assert "WORKDIR /app" in result
        assert "USER 1001" in result

    def test_generic_code_block_with_from(self):
        """Generic ``` block starting with FROM."""
        raw = (
            "```\n"
            "FROM ubi9/nodejs-22\n"
            "COPY . .\n"
            "RUN npm install\n"
            "```\n"
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM ubi9/nodejs-22")

    def test_write_file_tool_call_with_escaped_newlines(self):
        """write_file tool call as text with \\n escape sequences (Qwen pattern)."""
        raw = (
            '{"name": "render_template", "arguments": {"template_name": "Dockerfile.ubi.j2"}}\n'
            "\n"
            "After rendering the template, I'll write the Dockerfile.\n"
            "\n"
            '{"name": "write_file", "arguments": {"path": '
            '"/workspace/myproject/Dockerfile.ubi", "content": '
            '"FROM registry.access.redhat.com/ubi9/python-312\\n\\n'
            "WORKDIR /opt/app-root/src\\n\\n"
            "COPY . ./\\n\\n"
            'RUN pip install --no-cache-dir .\\n\\n'
            'USER 1001\\n"}}\n'
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM registry.access.redhat.com/ubi9/python-312")
        assert "WORKDIR /opt/app-root/src" in result
        assert "pip install" in result
        assert "USER 1001" in result

    def test_write_file_tool_call_with_literal_newlines(self):
        """write_file tool call where the content has real newlines (not just \\n).

        This is the exact pattern from the debug dump that was failing:
        the LLM output has real newlines between JSON objects AND escaped
        newlines inside the content field.
        """
        raw = (
            '{"name": "write_file", "arguments": {"path": '
            '"/workspace/composio/python/providers/crewai/Dockerfile.ubi", '
            '"content": "FROM registry.access.redhat.com/ubi9/python-312\\n'
            "\\nENV COMPOSIO_API_KEY=\\n\\nWORKDIR /opt/app-root/src\\n\\n"
            "COPY python/providers/crewai/ ./\\n\\n"
            "RUN pip install --no-cache-dir -r requirements.txt\\n\\n"
            'USER 1001\\n"}}'
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM registry.access.redhat.com/ubi9/python-312")
        assert "COMPOSIO_API_KEY" in result
        assert "pip install" in result
        assert "USER 1001" in result

    def test_write_file_with_escaped_quotes(self):
        """write_file content with escaped quotes (e.g. ENTRYPOINT [\"node\"])."""
        raw = (
            '{"name": "write_file", "arguments": {"path": '
            '"/workspace/app/Dockerfile.ubi", "content": '
            '"FROM ubi9/nodejs-22\\n'
            "COPY . .\\n"
            'ENTRYPOINT [\\"node\\"]\\n'
            'CMD [\\"index.ts\\"]\\n"}}'
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert 'ENTRYPOINT ["node"]' in result
        assert 'CMD ["index.ts"]' in result

    def test_write_file_with_preceding_render_template_and_text(self):
        """Full Qwen pattern: render_template JSON + text + write_file JSON + dockerignore."""
        raw = (
            '{"name": "render_template", "arguments": {"template_name": '
            '"Dockerfile.ubi.j2", "variables": {"base_image": "ubi9/python-312"}}}\n'
            "\n"
            "After rendering the template, I'll write the Dockerfile.ubi.\n"
            "\n"
            '{"name": "write_file", "arguments": {"path": '
            '"/workspace/app/Dockerfile.ubi", "content": '
            '"FROM ubi9/python-312\\nWORKDIR /app\\nCOPY . .\\nRUN pip install .\\n'
            'USER 1001\\n"}}\n'
            "\n"
            '{"name": "write_file", "arguments": {"path": '
            '"/workspace/app/.dockerignore", "content": ".git\\nnode_modules\\n"}}\n'
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM ubi9/python-312")
        # Should extract the Dockerfile, not the .dockerignore
        assert ".git" not in result
        assert "WORKDIR /app" in result

    def test_write_file_content_before_path(self):
        """write_file with content field before path field."""
        raw = (
            '{"name": "write_file", "arguments": {"content": '
            '"FROM ubi9/python-312\\nCOPY . .\\nUSER 1001\\n", '
            '"path": "/workspace/app/Dockerfile.ubi"}}'
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM ubi9/python-312")

    def test_bare_from_line(self):
        """Bare FROM at start of a line with no code block."""
        raw = (
            "I'll create the following Dockerfile:\n"
            "FROM ubi9/python-312\n"
            "WORKDIR /app\n"
            "COPY . .\n"
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is not None
        assert result.startswith("FROM ubi9/python-312")

    def test_no_dockerfile_content(self):
        """Response with no recognizable Dockerfile content."""
        raw = "I analyzed the project and it needs a Python-based container."
        result = _extract_dockerfile_from_response(raw)
        assert result is None

    def test_empty_response(self):
        """Empty LLM response."""
        assert _extract_dockerfile_from_response("") is None
        assert _extract_dockerfile_from_response("   ") is None

    def test_write_file_for_non_dockerfile_ignored(self):
        """write_file for .dockerignore or other files should be ignored."""
        raw = (
            '{"name": "write_file", "arguments": {"path": '
            '"/workspace/app/.dockerignore", "content": ".git\\nnode_modules\\n"}}'
        )
        result = _extract_dockerfile_from_response(raw)
        assert result is None


class TestUsesMinimalBase:
    """Tests for _uses_minimal_base detection."""

    def test_full_ubi_image(self):
        assert not _uses_minimal_base("FROM registry.access.redhat.com/ubi9/python-312\n")

    def test_minimal_ubi_image(self):
        assert _uses_minimal_base("FROM registry.access.redhat.com/ubi9-minimal\n")

    def test_ubi_minimal_path(self):
        assert _uses_minimal_base("FROM registry.access.redhat.com/ubi9/minimal\n")

    def test_no_from(self):
        assert not _uses_minimal_base("WORKDIR /app\nCOPY . .\n")


class TestFixupDockerfile:
    """Tests for deterministic Dockerfile post-processing fixes."""

    def test_microdnf_to_dnf_on_full_image(self, tmp_path: Path):
        """microdnf should be replaced with dnf on full UBI images."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/python-312\n"
            "RUN microdnf install -y gcc && microdnf clean all\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "microdnf" not in content
        assert "dnf install -y gcc" in content
        assert "dnf clean all" in content

    def test_dnf_to_microdnf_on_minimal_image(self, tmp_path: Path):
        """dnf should be replaced with microdnf on minimal UBI images."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9-minimal\n"
            "RUN dnf install -y gcc && dnf clean all\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "dnf " not in content.replace("microdnf", "")
        assert "microdnf install -y gcc" in content

    def test_chgrp_wrapped_with_user_0(self, tmp_path: Path):
        """chgrp without USER 0 should be wrapped."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/python-312\n"
            "COPY . .\n"
            "RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root\n"
            "CMD [\"python\", \"app.py\"]\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        lines = content.strip().split("\n")
        # Find the chgrp line and verify USER 0 is before it
        for i, line in enumerate(lines):
            if "chgrp" in line:
                assert lines[i - 1].strip() == "USER 0"
                assert lines[i + 1].strip().startswith("USER ")
                break
        else:
            pytest.fail("chgrp line not found")

    def test_chgrp_already_root_not_wrapped(self, tmp_path: Path):
        """chgrp with USER 0 already set should NOT be double-wrapped."""
        df = tmp_path / "Dockerfile.ubi"
        original = (
            "FROM registry.access.redhat.com/ubi9/python-312\n"
            "USER 0\n"
            "RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root\n"
            "USER 1001\n"
        )
        df.write_text(original)
        _fixup_dockerfile(df)
        content = df.read_text()
        # Should not be modified
        assert content == original

    def test_npm_install_as_root_gets_chgrp_fix(self, tmp_path: Path):
        """npm install as root then USER switch should add chgrp for node_modules."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/nodejs-22\n"
            "USER root\n"
            "RUN npm ci\n"
            "USER 1001\n"
            "COPY . .\n"
            "RUN npm run build\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "chgrp -R 0 /opt/app-root/src/node_modules" in content
        assert "chmod -R g=u /opt/app-root/src/node_modules" in content
        # The chgrp should be BEFORE the USER 1001 line
        chgrp_pos = content.index("chgrp -R 0 /opt/app-root/src/node_modules")
        user_pos = content.index("USER 1001")
        assert chgrp_pos < user_pos

    def test_dnf_install_without_root_gets_wrapped(self, tmp_path: Path):
        """dnf install without USER 0 should be wrapped with USER 0."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/nodejs-22\n"
            "RUN dnf install -y gcc make && dnf clean all\n"
            "COPY . .\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        lines = content.strip().split("\n")
        for i, line in enumerate(lines):
            if "dnf install" in line:
                assert lines[i - 1].strip() == "USER 0"
                assert lines[i + 1].strip().startswith("USER ")
                break
        else:
            pytest.fail("dnf install line not found")

    def test_dnf_install_multiline_wrapped_correctly(self, tmp_path: Path):
        """Multi-line RUN dnf install should have USER 1001 AFTER all continuation lines."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/nodejs-22\n"
            "RUN dnf install -y gcc \\\n"
            "    make \\\n"
            "    curl && \\\n"
            "    dnf clean all\n"
            "COPY . .\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        lines = content.strip().split("\n")
        # Find USER 0 and USER 1001
        user0_idx = None
        user1001_idx = None
        dnf_idx = None
        clean_idx = None
        for idx, ln in enumerate(lines):
            if ln.strip() == "USER 0":
                user0_idx = idx
            if ln.strip().startswith("USER 1001"):
                user1001_idx = idx
            if "dnf install" in ln:
                dnf_idx = idx
            if "dnf clean all" in ln:
                clean_idx = idx
        assert user0_idx is not None, "USER 0 not found"
        assert user1001_idx is not None, "USER 1001 not found"
        assert dnf_idx is not None, "dnf install not found"
        assert clean_idx is not None, "dnf clean all not found"
        # USER 0 before dnf install
        assert user0_idx < dnf_idx
        # dnf clean all before USER 1001
        assert clean_idx < user1001_idx
        # No USER directive between dnf install and dnf clean all
        for idx in range(dnf_idx, clean_idx + 1):
            assert not lines[idx].strip().startswith("USER "), \
                f"Found USER directive inside multi-line RUN at line {idx}: {lines[idx]}"

    def test_dnf_install_already_root_not_wrapped(self, tmp_path: Path):
        """dnf install with USER 0 already set should NOT be wrapped."""
        df = tmp_path / "Dockerfile.ubi"
        original = (
            "FROM registry.access.redhat.com/ubi9/nodejs-22\n"
            "USER 0\n"
            "RUN dnf install -y gcc && dnf clean all\n"
            "USER 1001\n"
        )
        df.write_text(original)
        _fixup_dockerfile(df)
        assert df.read_text() == original

    def test_no_fixup_needed(self, tmp_path: Path):
        """Clean Dockerfile should not be modified."""
        df = tmp_path / "Dockerfile.ubi"
        original = (
            "FROM registry.access.redhat.com/ubi9/python-312\n"
            "USER 0\n"
            "RUN dnf install -y gcc && dnf clean all\n"
            "COPY . .\n"
            "RUN pip install .\n"
            "RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root\n"
            "USER 1001\n"
        )
        df.write_text(original)
        _fixup_dockerfile(df)
        assert df.read_text() == original


class TestFixupBaseImage:
    """Tests for non-UBI base image replacement."""

    def test_node_replaced_with_ubi(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM node:16\nCOPY . .\nRUN npm install\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/nodejs-22" in content
        assert "node:16" not in content

    def test_python_replaced_with_ubi(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM python:3.11-slim\nCOPY . .\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/python-312" in content
        assert "python:3.11-slim" not in content

    def test_golang_replaced_with_ubi(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM golang:1.22\nCOPY . .\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/go-toolset" in content

    def test_alpine_replaced_with_ubi_minimal(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM alpine:3.19\nRUN apk add --no-cache curl\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/ubi-minimal" in content

    def test_nginx_replaced_with_ubi(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM nginx:latest\nCOPY dist/ /usr/share/nginx/html/\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/nginx-124" in content

    def test_ubi_image_not_modified(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        original = "FROM registry.access.redhat.com/ubi9/python-312\nCOPY . .\n"
        df.write_text(original)
        _fixup_dockerfile(df)
        assert df.read_text() == original

    def test_nvidia_cuda_not_modified(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        original = "FROM nvcr.io/nvidia/cuda:12.0-runtime-ubi9\nCOPY . .\n"
        df.write_text(original)
        _fixup_dockerfile(df)
        assert df.read_text() == original

    def test_multistage_as_alias_preserved(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM node:20 AS builder\nCOPY . .\nRUN npm run build\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/nodejs-22 AS builder" in content

    def test_java_openjdk_replaced(self, tmp_path: Path):
        df = tmp_path / "Dockerfile.ubi"
        df.write_text("FROM openjdk:21-slim\nCOPY target/*.jar app.jar\n")
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "registry.access.redhat.com/ubi9/openjdk-21" in content


class TestFixupPackageManagerMultiStage:
    """Tests for per-stage package manager fixup in multi-stage Dockerfiles."""

    def test_multistage_full_then_minimal(self, tmp_path: Path):
        """Builder uses full UBI (dnf), runtime uses minimal (microdnf)."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/ubi AS builder\n"
            "RUN microdnf install -y golang && microdnf clean all\n"
            "COPY . .\n"
            "RUN go build -o /app\n"
            "FROM registry.access.redhat.com/ubi9/ubi-minimal\n"
            "COPY --from=builder /app /app\n"
            "RUN dnf install -y libcurl && dnf clean all\n"
            "USER 1001\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        # Stage 1 (ubi full): microdnf should be replaced with dnf
        assert "dnf install -y golang" in content
        # Stage 2 (ubi-minimal): dnf should be replaced with microdnf
        assert "microdnf install -y libcurl" in content
        # Both install commands should be wrapped with USER 0
        assert content.count("USER 0") >= 2

    def test_multistage_both_correct_with_user(self, tmp_path: Path):
        """Both stages use correct package manager and USER 0 — no change."""
        df = tmp_path / "Dockerfile.ubi"
        original = (
            "FROM registry.access.redhat.com/ubi9/ubi AS builder\n"
            "USER 0\n"
            "RUN dnf install -y golang && dnf clean all\n"
            "USER 1001\n"
            "FROM registry.access.redhat.com/ubi9/ubi-minimal\n"
            "USER 0\n"
            "RUN microdnf install -y libcurl && microdnf clean all\n"
            "USER 1001\n"
        )
        df.write_text(original)
        _fixup_dockerfile(df)
        assert df.read_text() == original

    def test_single_stage_full_with_microdnf(self, tmp_path: Path):
        """Single stage full UBI with microdnf should still be fixed."""
        df = tmp_path / "Dockerfile.ubi"
        df.write_text(
            "FROM registry.access.redhat.com/ubi9/python-312\n"
            "RUN microdnf install -y gcc && microdnf clean all\n"
        )
        _fixup_dockerfile(df)
        content = df.read_text()
        assert "dnf install -y gcc" in content
        assert "microdnf" not in content
