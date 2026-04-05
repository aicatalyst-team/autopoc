"""Tests for autopoc.tools.template_tools module."""


from autopoc.tools.template_tools import get_available_templates, render_template


class TestGetAvailableTemplates:
    def test_lists_templates(self) -> None:
        templates = get_available_templates()
        assert "Dockerfile.ubi.j2" in templates
        assert "Dockerfile.ubi-builder.j2" in templates

    def test_returns_sorted_list(self) -> None:
        templates = get_available_templates()
        assert templates == sorted(templates)


class TestRenderTemplateSingleStage:
    def test_renders_basic_python(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi.j2",
                "variables": {
                    "base_image": "registry.access.redhat.com/ubi9/python-312",
                    "language": "python",
                    "component_name": "api",
                    "install_cmd": "pip install --no-cache-dir -r requirements.txt",
                    "expose_port": 8080,
                    "cmd": '["python", "app.py"]',
                },
            }
        )

        assert "FROM registry.access.redhat.com/ubi9/python-312" in result
        assert "pip install" in result
        assert "EXPOSE 8080" in result
        assert '["python", "app.py"]' in result
        assert "USER 1001" in result
        assert "chgrp -R 0" in result

    def test_no_system_packages(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi.j2",
                "variables": {
                    "base_image": "registry.access.redhat.com/ubi9/python-312",
                    "language": "python",
                    "component_name": "app",
                    "cmd": '["python", "main.py"]',
                },
            }
        )

        # Should not contain microdnf line
        assert "microdnf" not in result

    def test_with_system_packages(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi.j2",
                "variables": {
                    "base_image": "registry.access.redhat.com/ubi9/ubi-minimal",
                    "language": "python",
                    "component_name": "app",
                    "system_packages": ["gcc", "libffi-devel"],
                    "cmd": '["python", "main.py"]',
                },
            }
        )

        assert "microdnf install -y gcc libffi-devel" in result

    def test_no_expose_port(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi.j2",
                "variables": {
                    "base_image": "registry.access.redhat.com/ubi9/python-312",
                    "language": "python",
                    "component_name": "worker",
                    "cmd": '["python", "worker.py"]',
                },
            }
        )

        assert "EXPOSE" not in result


class TestRenderTemplateMultiStage:
    def test_renders_go_builder(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi-builder.j2",
                "variables": {
                    "builder_image": "registry.access.redhat.com/ubi9/go-toolset",
                    "build_cmd": "go build -o /build/app .",
                    "runtime_image": "registry.access.redhat.com/ubi9/ubi-minimal",
                    "language": "go",
                    "component_name": "api",
                    "build_artifact": "/build/app",
                    "expose_port": 8080,
                    "cmd": '["./app"]',
                },
            }
        )

        assert "FROM registry.access.redhat.com/ubi9/go-toolset AS builder" in result
        assert "go build" in result
        assert "FROM registry.access.redhat.com/ubi9/ubi-minimal" in result
        assert "COPY --from=builder /build/app ." in result
        assert "EXPOSE 8080" in result
        assert "USER 1001" in result

    def test_java_builder(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi-builder.j2",
                "variables": {
                    "builder_image": "registry.access.redhat.com/ubi9/openjdk-21",
                    "build_cmd": "mvn package -DskipTests",
                    "runtime_image": "registry.access.redhat.com/ubi9/openjdk-21-runtime",
                    "language": "java",
                    "component_name": "backend",
                    "build_artifact": "/build/target/app.jar",
                    "expose_port": 8080,
                    "cmd": '["java", "-jar", "app.jar"]',
                },
            }
        )

        assert "mvn package" in result
        assert "COPY --from=builder /build/target/app.jar ." in result


class TestRenderTemplateErrors:
    def test_nonexistent_template(self) -> None:
        result = render_template.invoke(
            {
                "template_name": "nonexistent.j2",
                "variables": {},
            }
        )
        assert "Error" in result
        assert "not found" in result
        assert "Available templates" in result

    def test_missing_variable_in_template(self) -> None:
        # Jinja2 with default settings renders missing vars as empty string
        # (undefined), so this should still render without error
        result = render_template.invoke(
            {
                "template_name": "Dockerfile.ubi.j2",
                "variables": {
                    "base_image": "ubi9/python-312",
                    "language": "python",
                    "component_name": "app",
                    # cmd is missing — Jinja2 will render it as empty
                },
            }
        )
        # Should still render (Jinja2 defaults to empty for undefined)
        assert "FROM ubi9/python-312" in result
