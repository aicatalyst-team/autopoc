"""Configuration management for AutoPoC.

Loads settings from environment variables or a .env file using pydantic-settings.
"""

from pydantic import Field, computed_field, model_validator
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
    llm_base_url: str | None = Field(
        default=None,
        description="Base URL for an OpenAI-compatible API (e.g. http://qwen-coder-svc.vllm:8000/v1)",
    )
    llm_api_key: str | None = Field(
        default=None,
        description="API key for the OpenAI-compatible endpoint (use 'none' if no auth required)",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model name to use (e.g., claude-3-5-sonnet-20241022, qwen2.5-coder-32b)",
    )
    llm_max_retries: int = Field(
        default=0,
        description="Max retries for LLM API calls (default 0 to fail fast on rate limits)",
    )
    llm_max_tokens: int | None = Field(
        default=None,
        description="Max output tokens for LLM responses (auto-detected per provider if unset)",
    )
    llm_fallback_enabled: bool = Field(
        default=True,
        description="When True and both a cloud provider (Anthropic/Vertex) and LLM_BASE_URL "
        "are configured, use the cloud provider as primary and LLM_BASE_URL as fallback "
        "on retryable errors (429, 500, 502, 503, 529). Set to False to disable fallback.",
    )

    # OGX LLM Proxy (for PoC projects that need LLM access)
    ogx_base_url: str | None = Field(
        default=None,
        description="OGX server URL for PoC projects "
        "(e.g. http://ogx-svc.ogx.svc.cluster.local:8321/v1). "
        "When set, PoC projects that need LLM access will be directed here.",
    )
    ogx_model: str = Field(
        default="qwen3-32b",
        description="Default model name to use on the OGX server.",
    )
    ogx_api_key: str = Field(
        default="none",
        description="API key for OGX server (use 'none' if no auth required).",
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
    quay_org: str | None = Field(
        default=None, description="Quay organization or username for pushed images"
    )
    quay_token: str | None = Field(
        default=None, description="Quay token (robot account token or OAuth token)"
    )
    quay_username: str | None = Field(
        default=None,
        description="Quay username for registry auth (e.g. 'myuser+robotname' for robot accounts). "
        "If unset, defaults to '$oauthtoken' (OAuth token auth).",
    )

    # OpenShift
    openshift_api_url: str | None = Field(
        default=None,
        description="OpenShift API URL (e.g. https://api.cluster.example.com:6443). "
        "Not required when running in-cluster (uses ServiceAccount auth).",
    )
    openshift_token: str | None = Field(
        default=None,
        description="OpenShift bearer token. "
        "Not required when running in-cluster (uses ServiceAccount auth).",
    )
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
        default=3, description="Max retry attempts for failed deployments"
    )
    max_container_fix_retries: int = Field(
        default=2,
        description="Max times apply can escalate to containerize to fix runtime container issues",
    )

    # Vale prose linting
    max_vale_revisions: int = Field(
        default=3,
        description="Max LLM revision passes when Vale finds prose issues in generated markdown",
    )

    # Google Sheet integration (for `run-sheet` command)
    sheet_credentials: str | None = Field(
        default=None,
        validation_alias="AUTOPOC_SHEET_CREDENTIALS",
        description="Path to Google service account credentials JSON for sheet access",
    )
    sheet_id: str | None = Field(
        default=None,
        validation_alias="AUTOPOC_SHEET_ID",
        description="Google Sheet ID containing PoC candidate projects",
    )
    max_evaluated_sheets: int = Field(
        default=4,
        description="Maximum number of sheet tabs to scan for candidates (leftmost first)",
    )
    max_batched_poc: int = Field(
        default=2,
        description="Maximum number of PoC pipelines to run in a single session",
    )
    max_monthly_pocs: int = Field(
        default=5,
        description="Maximum number of PoCs to run from monthly report (when monthly_mode=True)",
    )
    monthly_mode: bool = Field(
        default=True,
        validation_alias="AUTOPOC_MONTHLY_MODE",
        description="If True, read from monthly report tab instead of last N tabs",
    )
    target_month: str | None = Field(
        default=None,
        validation_alias="AUTOPOC_TARGET_MONTH",
        description="Target month for monthly mode in YYYY-MM format (defaults to current month)",
    )

    # Working directory
    work_dir: str = Field(
        default="/tmp/autopoc", description="Directory for cloned repos and temp files"
    )

    # Google Docs integration (for blog-create skill)
    google_docs_credentials: str | None = Field(
        default=None,
        description="Path to Google service account credentials JSON for Docs API access",
    )
    google_docs_folder_id: str | None = Field(
        default=None, description="Google Drive folder ID where blog docs should be created"
    )

    @model_validator(mode="after")
    def validate_llm_config(self) -> "AutoPoCConfig":
        """Ensure we have at least one LLM provider configured.

        When both a cloud provider and LLM_BASE_URL are set, the cloud provider
        is primary and LLM_BASE_URL becomes the fallback on retryable errors.
        """
        if not self.anthropic_api_key and not self.vertex_project and not self.llm_base_url:
            raise ValueError(
                "At least one LLM provider must be configured: "
                "ANTHROPIC_API_KEY, VERTEX_PROJECT, or LLM_BASE_URL."
            )
        if self.vertex_project and not self.vertex_location:
            # Default to us-east5 (where Claude is supported) if project is provided but location is not
            self.vertex_location = "us-east5"
        if self.llm_base_url and not self.llm_model:
            raise ValueError(
                "LLM_MODEL is required when using LLM_BASE_URL (e.g. LLM_MODEL=qwen2.5-coder-32b)."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_cloud_provider(self) -> bool:
        """Whether a cloud LLM provider (Anthropic/Vertex) is configured."""
        return bool(self.anthropic_api_key or self.vertex_project)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_fallback_provider(self) -> bool:
        """Whether a fallback provider (LLM_BASE_URL) is available.

        Fallback is available when:
        1. A cloud provider is configured (primary)
        2. LLM_BASE_URL is also configured (fallback)
        3. LLM_FALLBACK_ENABLED is True
        """
        return self.has_cloud_provider and bool(self.llm_base_url) and self.llm_fallback_enabled

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
            "ogx_api_key",
            "google_docs_credentials",
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
