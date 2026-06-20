# YAML-Only Auto-Merge Workflow

**File**: `.github/workflows/auto-merge-yaml.yml`

## How It Works

### 1. Path Detection (`check-yaml-only` job)

When a PR is opened/updated, the workflow uses [`dorny/paths-filter@v3`](https://github.com/dorny/paths-filter) to check if **all modified files** are in the safe paths.

**Outcomes:**
- ✅ `yaml_only=true` → Only safe YAML files modified
- ❌ `yaml_only=false` → Some files outside safe paths detected

### 2. Approval Check & Auto-Merge (`auto-merge` job)

If the PR passes the path filter, the workflow:

1. **Checks if PR has approvals** using `gh pr view` command
2. **If approved**:
   - Enables auto-merge with squash strategy
   - Deletes the feature branch
   - Merges to main
3. **If not approved**:
   - Posts comment indicating PR is eligible for auto-merge
   - Waits for approval

### 3. Notifications

**If YAML-only (eligible for auto-merge):**
```
✅ This PR contains only YAML files from safe paths and is eligible 
for auto-merge once approved by a reviewer.
```

**If contains other files:**
```
⚠️ This PR contains changes outside the safe YAML paths. Auto-merge 
is disabled. Manual review and merge required.
```

---

## Trigger Events

The workflow runs on these PR events:
- `opened` — New PR created
- `synchronize` — New commit pushed to PR
- `reopened` — PR reopened
- `review_requested` — Someone requests a review

---

## Permissions Required

```yaml
permissions:
  pull-requests: read    # Read PR info
  contents: write        # Write to merge PR
```

These are already granted to GitHub Actions workflows by default, but are explicitly declared for clarity.

---

## Example Usage

### ✅ Auto-merge Example

**PR Title**: "Update Seattle Division boundaries"

**Changes**:
```
divisions/wa/local/seattle_12345_uuid.yaml  ← SAFE ✅
divisions/wa/local/tacoma_67890_uuid.yaml   ← SAFE ✅
```

**Workflow outcome**:
1. Path filter: `yaml_only=true` ✅
2. Approval: Awaits reviewer approval
3. On approval: Auto-merges with squash strategy

---

### ❌ Block Auto-Merge Example

**PR Title**: "Fix code and update divisions"

**Changes**:
```
src/utils/place_name.py                     ← NOT SAFE ❌
divisions/tx/local/austin_99999_uuid.yaml   ← SAFE ✅
```

**Workflow outcome**:
1. Path filter: `yaml_only=false` ❌
2. Comment posted: "Auto-merge is disabled"
3. Requires manual review and merge

---

## Configuration

### Merge Strategy

Currently configured for **squash merge**:
```yaml
--squash   # Combine all commits into one before merging
```

**To change merge strategy**, edit the workflow:
```yaml
# Current (squash):
gh pr merge ${{ github.event.pull_request.number }} --auto --squash

# For regular merge:
gh pr merge ${{ github.event.pull_request.number }} --auto --merge

# For rebase:
gh pr merge ${{ github.event.pull_request.number }} --auto --rebase
```

### Adding Safe Paths

To allow auto-merge of additional paths, edit the `filters` section:

```yaml
filters: |
  safe_paths:
    - 'divisions/**/*.yml'
    - 'divisions/**/*.yaml'
    - 'jurisdictions/**/*.yml'
    - 'jurisdictions/**/*.yaml'
    - 'data/**/*.yaml'        # ← Add new path
```

---

## Troubleshooting

### Q: My PR has only YAML changes but auto-merge didn't trigger

**A**: Check these:
1. ✅ Is the path in the safe list? (exact match required)
2. ✅ Is the PR approved? (need at least 1 approval)
3. ✅ Are there no branch protection rules blocking auto-merge?
4. ✅ Check workflow run logs at Actions tab

### Q: Can I approve my own PR for auto-merge?

**A**: That depends on your repo's branch protection rules. If self-approval is blocked, you'll need a second reviewer's approval.

### Q: How do I manually merge if auto-merge fails?

**A**: Use the GitHub UI or CLI:
```bash
# Manual merge
gh pr merge <PR-NUMBER> --squash
```

---

## Security Considerations

- ✅ **Safe paths are explicit** — Only listed directories auto-merge
- ✅ **Approval required** — Can't auto-merge without human review
- ✅ **Branch protection compatible** — Respects repo branch rules
- ✅ **Limited permissions** — Uses standard `GITHUB_TOKEN` with minimal scope

---

## Related

- **Safe YAML paths**: `divisions/**/*.{yml,yaml}`, `jurisdictions/**/*.{yml,yaml}`
- **Main CI workflow**: `.github/workflows/ci.yml` (runs tests and lint)
- **Branch protection**: Configure in Settings → Branches → Branch protection rules
