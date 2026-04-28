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

    # Fork target
    fork_target: str = Field(
        default="gitlab",
        description="Where to fork repos: 'gitlab' or 'github'",
    )

    # GitLab (required when fork_target=gitlab)
    gitlab_url: str | None = Field(
        default=None, description="GitLab instance URL (e.g. https://gitlab.example.com)"
    )
    gitlab_token: str | None = Field(default=None, description="GitLab personal access token")
    gitlab_group: str | None = Field(
        default=None, description="GitLab group/namespace for forked repos"
    )

    # GitHub (required when fork_target=github)
    github_token: str | None = Field(default=None, description="GitHub personal access token")
    github_org: str | None = Field(
        default=None,
        description="GitHub organization for forks (if unset, forks to authenticated user)",
    )

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

    # Build strategy
    build_strategy: str = Field(
        default="podman",
        description="Container build strategy: 'podman' (local CLI) or 'openshift' (on-cluster builds)",
    )

    # Build retries
    max_build_retries: int = Field(
        default=3, description="Max retry attempts for failed container builds"
    )
    max_deploy_retries: int = Field(
        default=2, description="Max retry attempts for failed deployments"
    )
    max_container_fix_retries: int = Field(
        default=2,
        description="Max times apply can escalate to containerize to fix runtime container issues",
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

    @model_validator(mode="after")
    def validate_build_strategy(self) -> "AutoPoCConfig":
        """Validate build strategy."""
        if self.build_strategy not in ("podman", "openshift"):
            raise ValueError(
                f"BUILD_STRATEGY must be 'podman' or 'openshift', got '{self.build_strategy}'"
            )
        return self

    @model_validator(mode="after")
    def validate_fork_target(self) -> "AutoPoCConfig":
        """Validate fork target and its required credentials."""
        if self.fork_target not in ("gitlab", "github"):
            raise ValueError(f"FORK_TARGET must be 'gitlab' or 'github', got '{self.fork_target}'")
        if self.fork_target == "gitlab":
            missing = []
            if not self.gitlab_url:
                missing.append("GITLAB_URL")
            if not self.gitlab_token:
                missing.append("GITLAB_TOKEN")
            if not self.gitlab_group:
                missing.append("GITLAB_GROUP")
            if missing:
                raise ValueError(f"FORK_TARGET=gitlab requires: {', '.join(missing)}")
        elif self.fork_target == "github":
            if not self.github_token:
                raise ValueError("FORK_TARGET=github requires GITHUB_TOKEN to be set")
        return self

    def masked_summary(self) -> dict[str, str]:
        """Return config as a dict with secrets masked for display."""

        def mask(value: str) -> str:
            if len(value) <= 8:
                return "****"
            return value[:4] + "****" + value[-4:]

        secret_fields = {
            "anthropic_api_key",
            "gitlab_token",
            "github_token",
            "quay_token",
            "openshift_token",
        }
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
