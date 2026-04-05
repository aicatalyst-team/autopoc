"""Configuration management for AutoPoC.

Loads settings from environment variables or a .env file using pydantic-settings.
"""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AutoPoCConfig(BaseSettings):
    """AutoPoC configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key for Claude")
    vertex_project: str | None = Field(
        default=None, description="Google Cloud project ID for Vertex AI"
    )
    vertex_location: str | None = Field(
        default=None, description="Google Cloud region for Vertex AI (e.g., us-east5)"
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model name to use (e.g., claude-3-5-sonnet-20241022 or claude-3-5-haiku@20241022)",
    )
    llm_max_retries: int = Field(
        default=0,
        description="Max retries for LLM API calls (default 0 to fail fast on rate limits)",
    )

    # GitLab
    gitlab_url: str = Field(description="GitLab instance URL (e.g. https://gitlab.example.com)")
    gitlab_token: str = Field(description="GitLab personal access token")
    gitlab_group: str = Field(description="GitLab group/namespace for forked repos")

    # Quay
    quay_registry: str = Field(default="quay.io", description="Quay registry hostname")
    quay_org: str = Field(description="Quay organization for pushed images")
    quay_token: str = Field(description="Quay robot account token for push access")

    # OpenShift
    openshift_api_url: str = Field(
        description="OpenShift API URL (e.g. https://api.cluster.example.com:6443)"
    )
    openshift_token: str = Field(description="OpenShift bearer token")
    openshift_namespace_prefix: str = Field(
        default="poc", description="Prefix for created namespaces (e.g. poc-myproject)"
    )

    # Build
    max_build_retries: int = Field(
        default=3, description="Max retry attempts for failed container builds"
    )

    # Working directory
    work_dir: str = Field(
        default="/tmp/autopoc", description="Directory for cloned repos and temp files"
    )

    @model_validator(mode="after")
    def validate_llm_config(self) -> "AutoPoCConfig":
        """Ensure we have either Anthropic API key or Vertex AI config."""
        if not self.anthropic_api_key and not self.vertex_project:
            raise ValueError("Either ANTHROPIC_API_KEY or VERTEX_PROJECT must be provided.")
        if self.vertex_project and not self.vertex_location:
            # Default to us-east5 (where Claude is supported) if project is provided but location is not
            self.vertex_location = "us-east5"
        return self

    def masked_summary(self) -> dict[str, str]:
        """Return config as a dict with secrets masked for display."""

        def mask(value: str) -> str:
            if len(value) <= 8:
                return "****"
            return value[:4] + "****" + value[-4:]

        secret_fields = {"anthropic_api_key", "gitlab_token", "quay_token", "openshift_token"}
        result = {}
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            if value is None:
                result[field_name] = "None"
            elif field_name in secret_fields:
                result[field_name] = mask(str(value))
            else:
                result[field_name] = str(value)
        return result


def load_config() -> AutoPoCConfig:
    """Load and validate configuration from environment.

    Raises:
        pydantic.ValidationError: If required environment variables are missing.
    """
    return AutoPoCConfig()  # type: ignore[call-arg]
