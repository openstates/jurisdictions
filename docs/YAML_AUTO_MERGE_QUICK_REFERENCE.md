# Auto-Merge YAML PR Workflow — Quick Reference

## ✅ What Gets Auto-Merged

A PR will **automatically merge** when:
1. **All changes are in safe YAML paths**:
   ```
   divisions/**/*.{yml,yaml}
   jurisdictions/**/*.{yml,yaml}
   ```
2. **At least one reviewer has approved the PR**
3. **No branch protection rules are blocking**

## ❌ What Doesn't Auto-Merge

- ❌ Code changes (`.py` files, etc.)
- ❌ Config changes (`pyproject.toml`, `.github/`, etc.)
- ❌ Documentation (`.md` files, `/docs/`, etc.)
- ❌ PRs without approvals
- ❌ Any PR with **any** file outside the safe paths

## 📋 For Reviewers

When reviewing a YAML-only PR:
1. ✅ **Review the YAML changes** for accuracy
2. ✅ **Approve the PR** (one approval is enough)
3. 🤖 **Auto-merge happens automatically** (no manual merge needed)

```bash
# Example: after reviewing Seattle boundaries
# Just click "Approve" on GitHub, PR merges automatically
```

## 📝 For Contributors

### Making Manual YAML Changes

```bash
# 1. Create a feature branch
git checkout -b fix/update-seattle-boundaries

# 2. Edit YAML files only
nano divisions/wa/local/seattle_12345_uuid.yaml

# 3. Commit and push
git add divisions/wa/local/seattle_12345_uuid.yaml
git commit -m "Update Seattle division boundaries"
git push origin fix/update-seattle-boundaries

# 4. Create PR on GitHub
# → Workflow checks if files are YAML-only
# → If yes: "Eligible for auto-merge once approved"
# → Wait for approval, PR merges automatically
```

### Workflow Behavior

| Scenario | Path Check | Approval | Result |
|----------|-----------|----------|--------|
| YAML-only + approved | ✅ | ✅ | 🟢 Auto-merges |
| YAML-only + no approval | ✅ | ❌ | 🟡 Awaits approval |
| Code changes + approved | ❌ | ✅ | 🔴 Manual merge required |
| Code changes + no approval | ❌ | ❌ | 🔴 Manual merge required |

## 🔍 Debugging

### Check if your PR will auto-merge

Look at the workflow run in the "Actions" tab:

1. **`check-yaml-only` job**: Did it pass?
   - ✅ `yaml_only=true` → Path filter passed
   - ❌ `yaml_only=false` → Some files outside safe paths

2. **`auto-merge` job**: Did it run?
   - ✅ Yes → Checking approval
   - ❌ No → Likely failed path check

3. **Approval check**: Does it show approval?
   - ✅ `approved=true` → PR will merge
   - ❌ `approved=false` → Awaiting approval

### Common Issues

**Issue**: "Auto-merge is disabled"
```
⚠️ This PR contains changes outside the safe YAML paths
```
**Solution**: Review your PR for non-YAML files. Remove any code/config changes.

**Issue**: PR isn't merging even after approval
**Solution**: 
- Check branch protection rules in Settings
- Ensure repo allows auto-merge
- Try manual merge: `gh pr merge <PR-NUMBER> --squash`

## 🔐 Security

- ✅ Auto-merge only affects **data files**, not code
- ✅ Requires **human approval** (can't auto-merge without review)
- ✅ Respects **branch protection rules**
- ✅ No elevated permissions needed

## 📚 Full Documentation

See `docs/YAML_AUTO_MERGE_WORKFLOW.md` for complete details:
- Configuration options
- Merge strategies
- Adding new safe paths
- Security considerations

---

**Questions?** Open an issue or check the workflow logs in Actions tab.
