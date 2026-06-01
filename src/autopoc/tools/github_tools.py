"""GitHub integration tools for AutoPoC repository management.

This module provides GitHub API integration for managing AutoPoC-created repositories,
including tagging with topics, detection of existing AutoPoC repositories, and
intelligent fork management with force-sync capabilities.
"""

import json
import subprocess
from typing import Optional

from langchain_core.tools import tool


@tool
def set_repository_topics(
    owner: str, repo: str, topics: list[str], github_token: Optional[str] = None
) -> str:
    """Set GitHub topics on a repository to mark it as AutoPoC-created.

    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        topics: List of topics to set (e.g., ["autopoc", "poc", "automated-deployment"])
        github_token: GitHub token (if not provided, uses environment variable)

    Returns:
        Status message about the operation
    """
    try:
        # Use gh CLI if available, fallback to direct API call
        topics_json = json.dumps({"names": topics})

        # Try using gh CLI first (it handles auth automatically)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{owner}/{repo}/topics", "-X", "PUT", "--input", "-"],
                input=topics_json,
                text=True,
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                response_data = json.loads(result.stdout) if result.stdout else {}
                set_topics = response_data.get("names", [])
                return f"Successfully set topics on {owner}/{repo}: {', '.join(set_topics)}"
            else:
                # Fall back to curl if gh CLI fails
                raise subprocess.CalledProcessError(result.returncode, "gh", result.stderr)

        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to curl with explicit token
            if not github_token:
                return f"Failed to set topics on {owner}/{repo}: GitHub token required and gh CLI not available"

            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-X",
                    "PUT",
                    f"https://api.github.com/repos/{owner}/{repo}/topics",
                    "-H",
                    f"Authorization: Bearer {github_token}",
                    "-H",
                    "Accept: application/vnd.github+json",
                    "-d",
                    topics_json,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                try:
                    response_data = json.loads(result.stdout)
                    if "names" in response_data:
                        set_topics = response_data["names"]
                        return f"Successfully set topics on {owner}/{repo}: {', '.join(set_topics)}"
                    elif "message" in response_data:
                        return f"Failed to set topics on {owner}/{repo}: {response_data['message']}"
                except json.JSONDecodeError:
                    return f"Failed to set topics on {owner}/{repo}: Invalid API response"

            return f"Failed to set topics on {owner}/{repo}: API call failed"

    except Exception as e:
        return f"Failed to set topics on {owner}/{repo}: {e}"


@tool
def get_repository_topics(owner: str, repo: str) -> dict:
    """Get GitHub topics for a repository.

    Args:
        owner: Repository owner (username or organization)
        repo: Repository name

    Returns:
        Dict with topics list and metadata
    """
    try:
        # Try using gh CLI first
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{owner}/{repo}/topics"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                response_data = json.loads(result.stdout)
                return {
                    "success": True,
                    "topics": response_data.get("names", []),
                    "repository": f"{owner}/{repo}",
                }
            else:
                return {
                    "success": False,
                    "error": f"gh CLI failed: {result.stderr}",
                    "topics": [],
                    "repository": f"{owner}/{repo}",
                }

        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to public API (no auth required for public repos)
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    f"https://api.github.com/repos/{owner}/{repo}/topics",
                    "-H",
                    "Accept: application/vnd.github+json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                try:
                    response_data = json.loads(result.stdout)
                    if "names" in response_data:
                        return {
                            "success": True,
                            "topics": response_data["names"],
                            "repository": f"{owner}/{repo}",
                        }
                    elif "message" in response_data:
                        return {
                            "success": False,
                            "error": response_data["message"],
                            "topics": [],
                            "repository": f"{owner}/{repo}",
                        }
                except json.JSONDecodeError:
                    pass

            return {
                "success": False,
                "error": "API call failed",
                "topics": [],
                "repository": f"{owner}/{repo}",
            }

    except Exception as e:
        return {"success": False, "error": str(e), "topics": [], "repository": f"{owner}/{repo}"}


@tool
def is_autopoc_repository(owner: str, repo: str) -> dict:
    """Check if a repository was created by AutoPoC by examining its topics.

    Args:
        owner: Repository owner (username or organization)
        repo: Repository name

    Returns:
        Dict with AutoPoC detection results and metadata
    """
    try:
        topics_result = get_repository_topics.invoke({"owner": owner, "repo": repo})

        if not topics_result["success"]:
            return {
                "is_autopoc": False,
                "confidence": "unknown",
                "reason": f"Could not retrieve topics: {topics_result['error']}",
                "topics": [],
                "repository": f"{owner}/{repo}",
            }

        topics = topics_result["topics"]

        # Check for AutoPoC-specific topics
        autopoc_indicators = ["autopoc", "poc", "automated-deployment"]
        found_indicators = [topic for topic in topics if topic in autopoc_indicators]

        if "autopoc" in topics:
            return {
                "is_autopoc": True,
                "confidence": "high",
                "reason": "Repository has 'autopoc' topic",
                "topics": topics,
                "repository": f"{owner}/{repo}",
                "indicators": found_indicators,
            }
        elif len(found_indicators) >= 2:
            return {
                "is_autopoc": True,
                "confidence": "medium",
                "reason": f"Repository has multiple AutoPoC indicators: {', '.join(found_indicators)}",
                "topics": topics,
                "repository": f"{owner}/{repo}",
                "indicators": found_indicators,
            }
        elif len(found_indicators) >= 1:
            return {
                "is_autopoc": False,
                "confidence": "low",
                "reason": f"Repository has some indicators ({', '.join(found_indicators)}) but not conclusive",
                "topics": topics,
                "repository": f"{owner}/{repo}",
                "indicators": found_indicators,
            }
        else:
            return {
                "is_autopoc": False,
                "confidence": "high",
                "reason": "Repository has no AutoPoC indicators in topics",
                "topics": topics,
                "repository": f"{owner}/{repo}",
                "indicators": [],
            }

    except Exception as e:
        return {
            "is_autopoc": False,
            "confidence": "unknown",
            "reason": f"Error checking repository: {e}",
            "topics": [],
            "repository": f"{owner}/{repo}",
            "indicators": [],
        }


@tool
def check_github_repository_exists(owner: str, repo: str) -> dict:
    """Check if a GitHub repository exists and get basic metadata.

    Args:
        owner: Repository owner (username or organization)
        repo: Repository name

    Returns:
        Dict with existence check results and repository metadata
    """
    try:
        # Try using gh CLI first for better auth handling
        try:
            result = subprocess.run(
                [
                    "gh",
                    "repo",
                    "view",
                    f"{owner}/{repo}",
                    "--json",
                    "name,description,isPrivate,isFork,createdAt,updatedAt",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                repo_data = json.loads(result.stdout)
                return {
                    "exists": True,
                    "repository": f"{owner}/{repo}",
                    "metadata": {
                        "name": repo_data.get("name"),
                        "description": repo_data.get("description"),
                        "is_private": repo_data.get("isPrivate"),
                        "is_fork": repo_data.get("isFork"),
                        "created_at": repo_data.get("createdAt"),
                        "updated_at": repo_data.get("updatedAt"),
                    },
                }
            else:
                # Repository doesn't exist or no access
                return {
                    "exists": False,
                    "repository": f"{owner}/{repo}",
                    "error": result.stderr.strip()
                    if result.stderr
                    else "Repository not found or no access",
                }

        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to basic API check
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    f"https://api.github.com/repos/{owner}/{repo}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                status_code = result.stdout.strip()
                if status_code == "200":
                    return {
                        "exists": True,
                        "repository": f"{owner}/{repo}",
                        "metadata": "Limited metadata (public API check)",
                    }
                elif status_code == "404":
                    return {
                        "exists": False,
                        "repository": f"{owner}/{repo}",
                        "error": "Repository not found",
                    }
                elif status_code == "403":
                    return {
                        "exists": True,  # Exists but private/no access
                        "repository": f"{owner}/{repo}",
                        "error": "Repository exists but access forbidden",
                    }
                else:
                    return {
                        "exists": False,
                        "repository": f"{owner}/{repo}",
                        "error": f"Unexpected status code: {status_code}",
                    }

            return {"exists": False, "repository": f"{owner}/{repo}", "error": "API check failed"}

    except Exception as e:
        return {
            "exists": False,
            "repository": f"{owner}/{repo}",
            "error": f"Error checking repository: {e}",
        }


@tool
def force_sync_repository(
    target_repo: str, source_repo_url: str, work_dir: str = "/tmp/autopoc"
) -> str:
    """Force sync an existing AutoPoC repository with its source repository.

    Args:
        target_repo: Target repository in format "owner/repo"
        source_repo_url: URL of the source repository to sync from
        work_dir: Working directory for git operations

    Returns:
        Status message about sync operation
    """
    try:
        import shutil
        from pathlib import Path

        # Extract project name from target repo
        project_name = target_repo.split("/")[-1]
        work_path = Path(work_dir) / project_name

        # Clean up any existing work directory
        if work_path.exists():
            shutil.rmtree(work_path)

        work_path.mkdir(parents=True, exist_ok=True)

        results = []

        # Clone the target repository
        result = subprocess.run(
            ["git", "clone", f"https://github.com/{target_repo}.git", str(work_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            return f"Failed to clone target repository {target_repo}: {result.stderr}"

        results.append(f"Cloned target repository {target_repo}")

        # Add source repository as upstream remote
        result = subprocess.run(
            ["git", "remote", "add", "source", source_repo_url],
            cwd=work_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0 and "already exists" not in result.stderr:
            return f"Failed to add source remote: {result.stderr}"

        # Fetch from source repository
        result = subprocess.run(
            ["git", "fetch", "source"], cwd=work_path, capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            return f"Failed to fetch from source repository: {result.stderr}"

        results.append("Fetched source repository updates")

        # Get the default branch of the source repository
        result = subprocess.run(
            ["git", "ls-remote", "--symref", "source", "HEAD"],
            cwd=work_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        source_branch = "main"  # default fallback
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("ref: refs/heads/"):
                    source_branch = line.split("/")[-1]
                    break

        # Reset target main/master branch to source branch
        result = subprocess.run(
            ["git", "reset", "--hard", f"source/{source_branch}"],
            cwd=work_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            return f"Failed to reset to source branch: {result.stderr}"

        results.append(f"Reset to source/{source_branch}")

        # Force push to update the target repository
        result = subprocess.run(
            ["git", "push", "origin", "HEAD", "--force"],
            cwd=work_path,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            return f"Failed to force push updates: {result.stderr}"

        results.append("Force pushed updates to target repository")

        # Clean up work directory
        if work_path.exists():
            shutil.rmtree(work_path)

        return f"Successfully force-synced {target_repo}: {'; '.join(results)}"

    except Exception as e:
        return f"Failed to force-sync repository {target_repo}: {e}"


@tool
def list_autopoc_repositories(organization: str, github_token: Optional[str] = None) -> dict:
    """List all AutoPoC-created repositories in an organization.

    Args:
        organization: GitHub organization name
        github_token: GitHub token for API access

    Returns:
        Dict with list of AutoPoC repositories and metadata
    """
    try:
        autopoc_repos = []

        # Try using gh CLI first
        try:
            result = subprocess.run(
                [
                    "gh",
                    "repo",
                    "list",
                    organization,
                    "--json",
                    "name,description,isPrivate,createdAt,updatedAt",
                    "--limit",
                    "200",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                repos = json.loads(result.stdout)

                # Check each repository for AutoPoC topics
                for repo in repos:
                    repo_name = repo["name"]
                    autopoc_check = is_autopoc_repository.invoke(
                        {"owner": organization, "repo": repo_name}
                    )

                    if autopoc_check["is_autopoc"]:
                        autopoc_repos.append(
                            {
                                "name": repo_name,
                                "full_name": f"{organization}/{repo_name}",
                                "description": repo.get("description"),
                                "is_private": repo.get("isPrivate"),
                                "created_at": repo.get("createdAt"),
                                "updated_at": repo.get("updatedAt"),
                                "autopoc_confidence": autopoc_check["confidence"],
                                "autopoc_reason": autopoc_check["reason"],
                                "autopoc_indicators": autopoc_check.get("indicators", []),
                                "topics": autopoc_check.get("topics", []),
                            }
                        )

                return {
                    "success": True,
                    "organization": organization,
                    "total_repos_checked": len(repos),
                    "autopoc_repos": autopoc_repos,
                    "autopoc_count": len(autopoc_repos),
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to list repositories: {result.stderr}",
                    "organization": organization,
                    "autopoc_repos": [],
                }

        except (subprocess.CalledProcessError, FileNotFoundError):
            return {
                "success": False,
                "error": "gh CLI not available and no fallback implemented for organization repo listing",
                "organization": organization,
                "autopoc_repos": [],
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error listing AutoPoC repositories: {e}",
            "organization": organization,
            "autopoc_repos": [],
        }


@tool
def create_autopoc_fork(
    source_repo: str, target_org: str, autopoc_topics: Optional[list[str]] = None
) -> str:
    """Create a new GitHub fork and tag it as AutoPoC-created.

    Args:
        source_repo: Source repository in format "owner/repo"
        target_org: Target organization for the fork
        autopoc_topics: List of AutoPoC topics to add (uses default if not provided)

    Returns:
        Status message about fork creation and tagging
    """
    try:
        if autopoc_topics is None:
            autopoc_topics = ["autopoc", "poc", "automated-deployment", "openshift"]

        source_owner, source_name = source_repo.split("/")
        target_repo = f"{target_org}/{source_name}"

        results = []

        # Create the fork using gh CLI
        result = subprocess.run(
            ["gh", "repo", "fork", source_repo, "--org", target_org, "--clone=false"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return f"Failed to create fork {target_repo}: {result.stderr}"

        results.append(f"Created fork {target_repo}")

        # Add AutoPoC topics to the new fork
        topics_result = set_repository_topics.invoke(
            {"owner": target_org, "repo": source_name, "topics": autopoc_topics}
        )
        results.append(f"Topics: {topics_result}")

        return f"Successfully created AutoPoC fork: {'; '.join(results)}"

    except Exception as e:
        return f"Failed to create AutoPoC fork: {e}"
