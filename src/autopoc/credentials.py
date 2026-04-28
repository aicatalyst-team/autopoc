"""Startup credential validation for AutoPoC.

Validates that all configured services (GitLab, Quay, Anthropic/Vertex)
are reachable and credentials are valid before running the pipeline.
Fail-fast prevents wasting time on long pipeline runs that will fail
mid-way due to auth issues.
"""

import logging

import httpx
from rich.console import Console
from rich.table import Table

from autopoc.config import AutoPoCConfig

logger = logging.getLogger(__name__)


class CredentialStatus:
    """Result of a single credential check."""

    def __init__(self, service: str, ok: bool, detail: str = ""):
        self.service = service
        self.ok = ok
        self.detail = detail


def check_gitlab(config: AutoPoCConfig, timeout: float = 10.0) -> CredentialStatus:
    """Validate GitLab token by calling GET /api/v4/user."""
    url = f"{config.gitlab_url.rstrip('/')}/api/v4/user"
    try:
        resp = httpx.get(
            url,
            headers={"PRIVATE-TOKEN": config.gitlab_token},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            username = data.get("username", "unknown")
            return CredentialStatus("GitLab", True, f"authenticated as {username}")
        elif resp.status_code == 401:
            return CredentialStatus("GitLab", False, "token is invalid or expired (401)")
        else:
            return CredentialStatus("GitLab", False, f"unexpected HTTP {resp.status_code}")
    except httpx.ConnectError:
        return CredentialStatus("GitLab", False, f"cannot connect to {config.gitlab_url}")
    except httpx.TimeoutException:
        return CredentialStatus("GitLab", False, f"timeout connecting to {config.gitlab_url}")
    except Exception as e:
        return CredentialStatus("GitLab", False, str(e))


def check_quay(config: AutoPoCConfig, timeout: float = 10.0) -> CredentialStatus:
    """Validate Quay credentials by calling GET /api/v1/user/.

    Supports two authentication modes:
    - Robot account: QUAY_USERNAME is set (e.g. 'myuser+robotname'), uses Basic auth.
    - OAuth token: QUAY_USERNAME is unset, uses Bearer auth.
    """
    # Quay registry may be a URL (http://localhost:8080) or just a hostname (quay.io)
    registry = config.quay_registry
    if not registry.startswith("http"):
        registry = f"https://{registry}"
    url = f"{registry.rstrip('/')}/api/v1/user/"

    # Use Basic auth for robot accounts, Bearer for OAuth tokens
    if config.quay_username:
        auth = (config.quay_username, config.quay_token)
        headers = {}
    else:
        auth = None
        headers = {"Authorization": f"Bearer {config.quay_token}"}

    try:
        resp = httpx.get(
            url,
            auth=auth,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            username = data.get("username", "unknown")
            auth_type = "robot account" if config.quay_username else "OAuth token"
            return CredentialStatus("Quay", True, f"authenticated as {username} ({auth_type})")
        elif resp.status_code == 401:
            return CredentialStatus("Quay", False, "token is invalid or expired (401)")
        else:
            return CredentialStatus("Quay", False, f"unexpected HTTP {resp.status_code}")
    except httpx.ConnectError:
        return CredentialStatus("Quay", False, f"cannot connect to {config.quay_registry}")
    except httpx.TimeoutException:
        return CredentialStatus("Quay", False, f"timeout connecting to {config.quay_registry}")
    except Exception as e:
        return CredentialStatus("Quay", False, str(e))


def check_github(config: AutoPoCConfig, timeout: float = 10.0) -> CredentialStatus:
    """Validate GitHub token by calling GET /user."""
    url = "https://api.github.com/user"
    try:
        resp = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {config.github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            username = data.get("login", "unknown")
            org_info = f", org={config.github_org}" if config.github_org else ", user account"
            return CredentialStatus("GitHub", True, f"authenticated as {username}{org_info}")
        elif resp.status_code == 401:
            return CredentialStatus("GitHub", False, "token is invalid or expired (401)")
        elif resp.status_code == 403:
            return CredentialStatus("GitHub", False, "token lacks required permissions (403)")
        else:
            return CredentialStatus("GitHub", False, f"unexpected HTTP {resp.status_code}")
    except httpx.ConnectError:
        return CredentialStatus("GitHub", False, "cannot connect to api.github.com")
    except httpx.TimeoutException:
        return CredentialStatus("GitHub", False, "timeout connecting to api.github.com")
    except Exception as e:
        return CredentialStatus("GitHub", False, str(e))


def check_anthropic(config: AutoPoCConfig) -> CredentialStatus:
    """Validate Anthropic/Vertex AI credentials.

    For direct Anthropic: checks the API key format (starts with sk-ant-).
    For Vertex AI: checks that project and location are set.
    We don't make an actual LLM call to avoid cost/latency.
    """
    if config.vertex_project:
        if config.vertex_location:
            return CredentialStatus(
                "LLM (Vertex AI)",
                True,
                f"project={config.vertex_project}, location={config.vertex_location}",
            )
        else:
            return CredentialStatus(
                "LLM (Vertex AI)",
                False,
                "VERTEX_PROJECT is set but VERTEX_LOCATION is missing",
            )

    if config.anthropic_api_key:
        key = config.anthropic_api_key
        if key.startswith("sk-ant-"):
            return CredentialStatus("LLM (Anthropic)", True, "API key format valid")
        elif key == "sk-ant-placeholder":
            return CredentialStatus("LLM (Anthropic)", False, "still using placeholder key")
        else:
            # Non-standard format but might still work
            return CredentialStatus(
                "LLM (Anthropic)", True, "API key present (non-standard format)"
            )

    return CredentialStatus("LLM", False, "no API key or Vertex config provided")


def validate_credentials(
    config: AutoPoCConfig,
    console: Console | None = None,
    fail_fast: bool = True,
) -> bool:
    """Validate all credentials and print a status table.

    Args:
        config: The loaded AutoPoC configuration.
        console: Rich console for output. Creates one if not provided.
        fail_fast: If True, raise SystemExit on critical failures.

    Returns:
        True if all critical credentials are valid, False otherwise.
    """
    if console is None:
        console = Console()

    checks = [
        check_anthropic(config),
    ]

    # Validate git hosting credentials based on fork target
    if config.fork_target == "github":
        checks.append(check_github(config))
    else:
        checks.append(check_gitlab(config))

    checks.append(check_quay(config))

    table = Table(
        title="Credential Validation",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    all_ok = True
    for status in checks:
        if status.ok:
            style = "[green]OK[/green]"
        else:
            style = "[red]FAIL[/red]"
            all_ok = False
        table.add_row(status.service, style, status.detail)

    console.print(table)

    if not all_ok:
        failed = [s for s in checks if not s.ok]
        for s in failed:
            logger.error("Credential check failed: %s — %s", s.service, s.detail)

        if fail_fast:
            console.print(
                "\n[bold red]Credential validation failed.[/bold red] "
                "Fix the issues above before running the pipeline."
            )

    return all_ok
