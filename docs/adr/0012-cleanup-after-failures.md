# 12. Cleanup After Build and Deploy Failures

Date: 2025-06

## Status

Accepted

## Context

AutoPoC accumulates failed resources without cleanup:
- **Build failures** leave BuildConfigs, ImageStreams, and local images that consume storage
- **Deploy failures** leave orphaned pods and resources in namespaces that can interfere with retries
- **Repository management** lacks AutoPoC identification, leading to duplicate forks and manual cleanup
- **Fork logic** doesn't handle existing repositories intelligently

This leads to storage bloat, reduced retry success rates, and operational overhead.

## Decision

Implement aggressive cleanup with a "keep max 1 failure" policy:

### 1. Build Failure Cleanup
- Clean up previous build artifacts before each retry (Phase 5)
- Support both OpenShift (BuildConfigs/ImageStreams/pods) and Podman (local images) strategies
- Preserve current failure information for debugging
- Integration point: Before Phase 5 when `build_retries > 0`

### 2. Deployment Failure Cleanup  
- Clean up failed deployment resources before each retry (Phase 7)
- Capture pod logs and events before cleanup for debugging
- Reset namespace to clean state to avoid resource conflicts
- Integration point: Before Phase 7 when `deploy_retries > 0`

### 3. GitHub Repository Tagging
- Use GitHub Topics API to mark AutoPoC-created repositories
- Standard topics: `["autopoc", "poc", "automated-deployment", "openshift"]`
- Enable identification and batch management of AutoPoC repositories
- Support repository discovery and cleanup operations

### 4. Smart Fork Detection
- Check for existing repositories before fork creation
- Detect AutoPoC-created repositories using topics
- Force-sync existing AutoPoC repositories instead of failing
- Handle non-AutoPoC existing repositories gracefully

## Implementation

### New Tools Module
`src/autopoc/tools/cleanup_tools.py`:
- `cleanup_previous_build_failure()` - Clean build artifacts keeping current failure
- `cleanup_failed_deployment()` - Clean deployment resources with state capture
- `cleanup_openshift_build_resources()` - OpenShift-specific build cleanup
- `cleanup_local_build_images()` - Podman image cleanup

### GitHub Integration Module
`src/autopoc/tools/github_tools.py`:
- `set_repository_topics()` - Set AutoPoC topics on repositories
- `is_autopoc_repository()` - Check if repository was created by AutoPoC
- `force_sync_repository()` - Sync existing AutoPoC repository with source
- `list_autopoc_repositories()` - Find all AutoPoC repositories in organization

### Configuration Options
```python
# Cleanup policies  
cleanup_build_failures: bool = Field(default=True)
cleanup_deploy_failures: bool = Field(default=True)
keep_failure_logs: bool = Field(default=True)
max_build_history: int = Field(default=1)
max_deploy_history: int = Field(default=1)

# Repository management
github_autopoc_topics: list[str] = Field(default=["autopoc", "poc", "automated-deployment", "openshift"])
force_sync_existing_repos: bool = Field(default=True)
```

## Alternatives Considered

### Repository Identification
- **Repository descriptions**: Less structured than topics, harder to search
- **Branch names** (`autopoc-*`): Requires additional API calls, less reliable
- **File markers** (`.autopoc` files): Requires repo cloning to detect
- **GitHub topics** (chosen): Structured, searchable, accessible via API

### Cleanup Aggressiveness
- **No cleanup**: Current behavior, leads to resource accumulation
- **Retain all failures**: Better for debugging but storage intensive  
- **Time-based retention**: Complex policy management
- **Keep max 1 failure** (chosen): Balance between debugging and storage efficiency

### Integration Points
- **Post-failure cleanup**: Simpler but doesn't help with retry success
- **Pre-retry cleanup** (chosen): Improves retry success rates by avoiding conflicts
- **Background cleanup**: Adds complexity and potential race conditions

## Consequences

### Positive
- (+) Significant reduction in storage consumption from failed builds/deployments
- (+) Improved retry success rates due to clean state
- (+) Clear identification of AutoPoC-created repositories for management
- (+) Automated handling of existing repositories during fork operations
- (+) Reduced operational overhead for cleanup tasks

### Negative
- (-) Potential loss of debugging information if cleanup is too aggressive
- (-) Additional complexity in retry logic and error handling
- (-) Dependency on GitHub API for repository management features
- (-) Need for proper error handling if cleanup operations fail

### Mitigation
- Essential failure information preserved in `poc-state.yaml` before cleanup
- Configurable cleanup policies for different environments
- Graceful fallback if GitHub API operations fail
- Comprehensive logging of cleanup operations for audit trail

## Notes

This ADR addresses the four main cleanup improvement areas requested:
1. Build failure cleanup (never keep more than one failure)
2. Deploy failure cleanup with log preservation
3. GitHub repository tagging for AutoPoC identification 
4. Smart fork handling with force-sync for existing AutoPoC repositories

Implementation follows the existing patterns in the codebase and integrates with the current retry loop architecture.