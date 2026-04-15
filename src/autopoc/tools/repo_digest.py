"""Procedural repository summarizer.

Builds a compact text digest of a cloned repository without using an LLM.
The digest contains the file tree, build system info, README, key entry
points, existing Dockerfiles, CI/CD config, and extracted dependency names.

This replaces the pattern of giving an LLM file-reading tools and letting
it explore the repo — which is slow, expensive, and prone to step exhaustion.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories to skip entirely
SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".tox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "vendor",
    "dist",
    "build",
    "benchmarks",
    "benchmark",
    ".venv",
    "venv",
    "env",
}

# File extensions to skip in the tree listing
SKIP_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".o",
    ".a",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".pt",
    ".pth",
    ".onnx",
    ".safetensors",
    ".bin",
    ".h5",
    ".pkl",
    ".pickle",
    ".npy",
    ".npz",
    ".parquet",
    ".arrow",
    ".wasm",
    ".map",
}

# Build system indicator files, in priority order
BUILD_FILES = [
    # Python
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    # Node
    "package.json",
    # Go
    "go.mod",
    # Java
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    # Rust
    "Cargo.toml",
    # Ruby
    "Gemfile",
    # C/C++
    "CMakeLists.txt",
    "Makefile",
    # .NET
    # (*.csproj handled separately)
]

# Entry point files to look for (checked in order, first N found are read)
ENTRY_POINTS = [
    # Python
    "__main__.py",
    "main.py",
    "app.py",
    "server.py",
    "run.py",
    "cli.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    # Node
    "index.js",
    "index.ts",
    "server.js",
    "server.ts",
    "app.js",
    "app.ts",
    "main.js",
    "main.ts",
    # Go
    "main.go",
    "cmd/main.go",
    # Rust
    "src/main.rs",
    "src/lib.rs",
    # Java
    "src/main/java/Main.java",
]

# README filenames in priority order
README_FILES = ["README.md", "README.rst", "README.txt", "README"]

# Max chars for each section
MAX_TREE_CHARS = 3000
MAX_README_CHARS = 4000
MAX_BUILD_FILE_CHARS = 3000
MAX_ENTRY_POINT_CHARS = 800  # per file
MAX_ENTRY_POINTS = 3
MAX_DOCKERFILE_CHARS = 2000
MAX_TOTAL_CHARS = 20_000


def _read_file_safe(path: Path, max_chars: int) -> str:
    """Read a file, returning at most max_chars. Returns empty on error."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n... [truncated at {max_chars} chars]"
        return content
    except Exception:
        return ""


def _build_file_tree(repo_path: Path, max_chars: int = MAX_TREE_CHARS) -> str:
    """Build a compact file tree listing with sizes."""
    lines = []
    file_count = 0
    max_entries = 300

    for root, dirs, files in os.walk(repo_path):
        # Filter out skip dirs (modify in-place to prevent os.walk from descending)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))

        rel_root = Path(root).relative_to(repo_path)
        depth = len(rel_root.parts)

        # Show directory name
        if depth > 0:
            indent = "  " * (depth - 1)
            lines.append(f"{indent}{rel_root.name}/")

        # Show files
        for fname in sorted(files):
            if file_count >= max_entries:
                lines.append(f"  ... [{file_count}+ files total, listing truncated]")
                return "\n".join(lines)

            fpath = Path(root) / fname
            suffix = fpath.suffix.lower()

            # Skip binary/generated files
            if suffix in SKIP_EXTENSIONS:
                continue
            if fname.startswith("."):
                continue

            # Get file size
            try:
                size = fpath.stat().st_size
            except OSError:
                size = 0

            indent = "  " * depth
            if size > 100_000:
                size_str = f" ({size // 1024}KB)"
            elif size > 10_000:
                size_str = f" ({size // 1024}KB)"
            else:
                size_str = ""

            lines.append(f"{indent}{fname}{size_str}")
            file_count += 1

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... [tree truncated]"
    return result


def _find_readme(repo_path: Path) -> str:
    """Find and read the README file."""
    for name in README_FILES:
        readme_path = repo_path / name
        if readme_path.is_file():
            return _read_file_safe(readme_path, MAX_README_CHARS)
    return ""


def _find_build_file(repo_path: Path) -> tuple[str, str]:
    """Find the primary build/dependency file. Returns (filename, content)."""
    for name in BUILD_FILES:
        build_path = repo_path / name
        if build_path.is_file():
            return name, _read_file_safe(build_path, MAX_BUILD_FILE_CHARS)

    # Check for .csproj files
    for csproj in repo_path.glob("*.csproj"):
        return csproj.name, _read_file_safe(csproj, MAX_BUILD_FILE_CHARS)

    return "", ""


def _find_entry_points(repo_path: Path) -> list[tuple[str, str]]:
    """Find and read entry point files. Returns list of (path, content)."""
    found = []

    # Check root-level entry points
    for name in ENTRY_POINTS:
        ep_path = repo_path / name
        if ep_path.is_file():
            content = _read_file_safe(ep_path, MAX_ENTRY_POINT_CHARS)
            if content:
                found.append((name, content))
                if len(found) >= MAX_ENTRY_POINTS:
                    return found

    # Check for __init__.py in top-level packages (to see version/imports)
    for child in sorted(repo_path.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and child.name not in SKIP_DIRS:
            init_path = child / "__init__.py"
            if init_path.is_file():
                content = _read_file_safe(init_path, MAX_ENTRY_POINT_CHARS)
                if content:
                    rel = str(init_path.relative_to(repo_path))
                    found.append((rel, content))
                    if len(found) >= MAX_ENTRY_POINTS:
                        return found

    return found


def _find_dockerfiles(repo_path: Path) -> list[tuple[str, str]]:
    """Find existing Dockerfiles."""
    results = []
    patterns = ["Dockerfile", "Dockerfile.*", "*.dockerfile"]
    seen = set()
    for pattern in patterns:
        for df in repo_path.glob(pattern):
            if df.is_file() and df.name not in seen:
                seen.add(df.name)
                content = _read_file_safe(df, MAX_DOCKERFILE_CHARS)
                results.append((df.name, content))
    return results


def _find_compose(repo_path: Path) -> str | None:
    """Find docker-compose file."""
    for name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        compose_path = repo_path / name
        if compose_path.is_file():
            return _read_file_safe(compose_path, 2000)
    return None


def _detect_cicd(repo_path: Path) -> str | None:
    """Detect CI/CD system."""
    checks = [
        (".github/workflows", "github-actions"),
        (".gitlab-ci.yml", "gitlab-ci"),
        ("Jenkinsfile", "jenkins"),
        (".circleci", "circleci"),
        (".travis.yml", "travis"),
        ("cloudbuild.yaml", "cloudbuild"),
        ("azure-pipelines.yml", "azure-pipelines"),
    ]
    for path, name in checks:
        if (repo_path / path).exists():
            return name
    return None


def _extract_python_deps(content: str, filename: str) -> list[str]:
    """Extract dependency names from Python build files."""
    deps = []

    if filename == "requirements.txt":
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                # Extract package name (before any version specifier)
                name = (
                    line.split("==")[0]
                    .split(">=")[0]
                    .split("<=")[0]
                    .split("~=")[0]
                    .split("[")[0]
                    .strip()
                )
                if name:
                    deps.append(name)

    elif filename == "pyproject.toml":
        # Simple extraction from dependencies = [...] section
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies") and "=" in stripped:
                in_deps = True
                continue
            if in_deps:
                if stripped == "]":
                    break
                # Extract quoted package name
                if '"' in stripped:
                    pkg = stripped.strip('", ')
                    name = (
                        pkg.split(">=")[0]
                        .split("<=")[0]
                        .split("==")[0]
                        .split("~=")[0]
                        .split("[")[0]
                        .split("<")[0]
                        .split(">")[0]
                        .strip()
                    )
                    if name:
                        deps.append(name)

    return deps[:30]  # cap at 30


def _extract_node_deps(content: str) -> list[str]:
    """Extract dependency names from package.json."""
    import json

    try:
        data = json.loads(content)
        deps = list(data.get("dependencies", {}).keys())
        deps += list(data.get("devDependencies", {}).keys())
        return deps[:30]
    except (json.JSONDecodeError, AttributeError):
        return []


def build_repo_digest(repo_path: str, max_total_chars: int = MAX_TOTAL_CHARS) -> str:
    """Build a compact text digest of a repository.

    This is a purely procedural function — no LLM calls. It reads key files
    and produces a structured markdown summary suitable for LLM analysis.

    Args:
        repo_path: Absolute path to the cloned repository.
        max_total_chars: Maximum total characters in the output.

    Returns:
        A structured markdown string summarizing the repository.
    """
    root = Path(repo_path)
    if not root.is_dir():
        return f"Error: {repo_path} is not a directory"

    sections = []

    # Header
    repo_name = root.name
    sections.append(f"# Repository: {repo_name}\n")

    # File tree
    tree = _build_file_tree(root)
    if tree:
        sections.append(f"## File Structure\n```\n{tree}\n```\n")

    # Build system
    build_filename, build_content = _find_build_file(root)
    if build_filename:
        sections.append(f"## Build System: {build_filename}\n```\n{build_content}\n```\n")

        # Extract dependencies
        deps = []
        if build_filename in ("requirements.txt", "pyproject.toml"):
            deps = _extract_python_deps(build_content, build_filename)
        elif build_filename == "package.json":
            deps = _extract_node_deps(build_content)

        if deps:
            sections.append(f"**Key dependencies:** {', '.join(deps)}\n")
    else:
        sections.append("## Build System: not detected\n")

    # README
    readme = _find_readme(root)
    if readme:
        sections.append(f"## README\n{readme}\n")

    # Entry points
    entry_points = _find_entry_points(root)
    if entry_points:
        sections.append("## Entry Points\n")
        for name, content in entry_points:
            sections.append(f"### {name}\n```\n{content}\n```\n")

    # Existing Dockerfiles
    dockerfiles = _find_dockerfiles(root)
    if dockerfiles:
        sections.append("## Existing Dockerfiles\n")
        for name, content in dockerfiles:
            sections.append(f"### {name}\n```dockerfile\n{content}\n```\n")
    else:
        sections.append("## Existing Dockerfiles: none\n")

    # docker-compose
    compose = _find_compose(root)
    if compose:
        sections.append(f"## Docker Compose\n```yaml\n{compose}\n```\n")

    # CI/CD
    cicd = _detect_cicd(root)
    sections.append(f"## CI/CD: {cicd or 'none detected'}\n")

    # Helm / Kustomize
    has_helm = any(root.rglob("Chart.yaml"))
    has_kustomize = any(root.rglob("kustomization.yaml")) or any(root.rglob("kustomization.yml"))
    sections.append(f"## Helm chart: {'yes' if has_helm else 'no'}")
    sections.append(f"## Kustomize: {'yes' if has_kustomize else 'no'}\n")

    result = "\n".join(sections)

    if len(result) > max_total_chars:
        result = result[:max_total_chars] + "\n\n... [digest truncated]"

    logger.info("Built repo digest: %d chars for %s", len(result), repo_name)
    return result
