# GitHub Repository Safety

Use these rules for every GitHub repository AutoPoC creates or adopts, whether
it was created with `gh repo fork`, `gh repo create`, or the GitHub REST API.

## Protected default branch

Run this immediately after the repository exists and before any AutoPoC push.
The repository owner must have GitHub repository administration permissions for
the branch-protection API.

```bash
GITHUB_OWNER="${GITHUB_ORG:-$(gh api user --jq '.login')}"
GITHUB_REPO="$GITHUB_OWNER/$PROJECT_NAME"
GITHUB_DEFAULT_BRANCH=$(gh api "/repos/$GITHUB_REPO" --jq '.default_branch')
GITHUB_DEFAULT_BRANCH_PATH="${GITHUB_DEFAULT_BRANCH//\//%2F}"
: "${AUTOPOC_REQUIRED_STATUS_CHECKS_JSON:?Set AUTOPOC_REQUIRED_STATUS_CHECKS_JSON to a non-empty JSON array of required check names}"
if ! python -c 'import json, sys; checks = json.loads(sys.argv[1]); assert isinstance(checks, list) and checks and all(isinstance(check, str) and check for check in checks)' "$AUTOPOC_REQUIRED_STATUS_CHECKS_JSON"; then
  echo "ERROR: AUTOPOC_REQUIRED_STATUS_CHECKS_JSON must be a non-empty JSON array of check names"
  exit 1
fi

echo "Protecting GitHub default branch: $GITHUB_REPO:$GITHUB_DEFAULT_BRANCH"
if ! gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "/repos/$GITHUB_REPO/branches/$GITHUB_DEFAULT_BRANCH_PATH/protection" \
  --input - <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": $AUTOPOC_REQUIRED_STATUS_CHECKS_JSON
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false
}
JSON
then
  echo "ERROR: Could not protect $GITHUB_REPO:$GITHUB_DEFAULT_BRANCH"
  exit 1
fi
```

This protects whichever default branch the repository uses, including `main`
and `master`, without assuming one name. If the repository uses another
default branch, protect that branch too: AutoPoC must never silently leave the
default branch unprotected.

## AutoPoC write branch

The protected default branch is read-only for the pipeline. Use one dedicated
branch for source synchronization and generated code commits:

```bash
AUTOPOC_BRANCH="${AUTOPOC_BRANCH:-autopoc}"
git checkout -B "$AUTOPOC_BRANCH"
```

For GitHub, push only that branch:

```bash
git push origin "$AUTOPOC_BRANCH" --force
```

Do not use `git push origin --all`, `git push origin HEAD`, or an unqualified
`git push` in the GitHub path. Those forms can target `main` or `master` after
a clone or checkout. The `autopoc-artifacts` branch is also allowed for PoC
plans, test scripts, reports, and blog artifacts; it is not the protected
default branch.
