"""Template rendering tools for LangChain agents.

Provides a tool to render Jinja2 templates from the autopoc templates directory.
Used by the containerize agent to generate Dockerfile.ubi files and by the
deploy agent to generate K8s manifests.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from langchain_core.tools import tool

# Templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Jinja2 environment — loaded once
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def get_available_templates() -> list[str]:
    """Return a list of available template names."""
    return sorted(_env.list_templates(extensions=["j2"]))


@tool
def render_template(template_name: str, variables: dict) -> str:
    """Render a Jinja2 template with the given variables.

    Args:
        template_name: Name of the template file (e.g. "Dockerfile.ubi.j2").
        variables: Dict of template variables to substitute.

    Returns:
        The rendered template content as a string.
    """
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        available = get_available_templates()
        return f"Error: template '{template_name}' not found. Available templates: {available}"

    try:
        return template.render(**variables)
    except Exception as e:
        return f"Error rendering template '{template_name}': {e}"
