"""Configuration management for AutoPoC.

Loads settings from environment variables or a .env file using pydantic-settings.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AutoPoCConfig(BaseSettings):
    """AutoPoC configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Environment variables take priority over .env file values
        env_priority="environment",
    )

    # LLM
    anthropic_api_key: str = Field(description="Anthropic API key for Claude")
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
            if field_name in secret_fields:
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
