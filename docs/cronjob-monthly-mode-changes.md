# CronJob Changes for Monthly Mode Default

This document describes the changes made to the AutoPoC cronjob configuration to support monthly mode as the default behavior.

## Changes Made

### 1. **Environment Variables Added**

The following new environment variables have been added to both the cronjob (`deploy/base/cronjob.yaml`) and job template (`deploy/base/job.yaml`):

```yaml
# --- Monthly Mode configuration (default behavior) ---
- name: AUTOPOC_MONTHLY_MODE
  valueFrom:
    secretKeyRef:
      name: autopoc-credentials
      key: AUTOPOC_MONTHLY_MODE
      optional: true
- name: AUTOPOC_TARGET_MONTH
  valueFrom:
    secretKeyRef:
      name: autopoc-credentials
      key: AUTOPOC_TARGET_MONTH
      optional: true
- name: MAX_MONTHLY_POCS
  valueFrom:
    secretKeyRef:
      name: autopoc-credentials
      key: MAX_MONTHLY_POCS
      optional: true
```

### 2. **Secret Template Updated**

The secret template (`deploy/overlays/example/secret.yaml.example`) now includes documentation for the new monthly mode variables:

```yaml
# ═══════════════════════════════════════════════════════════
# Monthly Mode (default behavior for run-sheet)
# ═══════════════════════════════════════════════════════════

# Monthly mode enabled by default - set to "false" to use legacy mode
# AUTOPOC_MONTHLY_MODE: "false"

# Target month for monthly mode in YYYY-MM format (defaults to current month)  
# AUTOPOC_TARGET_MONTH: "2026-05"

# Maximum number of PoCs to run from monthly report (defaults to 5)
# MAX_MONTHLY_POCS: "3"
```

### 3. **Prompt Updated**

The cronjob prompt has been updated to be more specific about monthly mode behavior:

**Before:**
```yaml
- "Read candidates from the Google Sheet and run PoCs for the top picks"
```

**After:**
```yaml
- "Read approved projects from this month's report tab and run up to 5 PoCs"
```

### 4. **Documentation Updated**

The cronjob header comment now mentions monthly mode:

```yaml
# AutoPoC CronJob (OpenCode harness) — runs `run-sheet` daily at midnight UTC.
# Uses monthly mode by default to process current month's approved projects.
# Credentials come from the autopoc-credentials Secret.
# Schedule and args can be overridden via overlay patches.
```

## Behavior Changes

### **Default Behavior (No Configuration)**

Without any monthly mode environment variables set:

- ✅ **Monthly mode enabled** by default
- ✅ **Current month** automatically detected (e.g., "2026-05")
- ✅ **Up to 5 PoCs** run per execution (up from 2 in legacy mode)
- ✅ **Daily runs** to catch newly approved projects throughout the month

### **Customization Options**

#### **Use Legacy Mode**
```yaml
AUTOPOC_MONTHLY_MODE: "false"
```

#### **Target Specific Month**
```yaml
AUTOPOC_TARGET_MONTH: "2026-04"  # Process April 2026 report
```

#### **Limit Number of PoCs**
```yaml
MAX_MONTHLY_POCS: "3"  # Run only 3 PoCs instead of 5
```

#### **Disable Monthly Mode Temporarily**
```yaml
AUTOPOC_MONTHLY_MODE: "false"
MAX_EVALUATED_SHEETS: "2"  # Use legacy mode with 2 tabs
```

## Migration Guide

### **For Existing Deployments**

1. **No action required** - monthly mode will work with existing configurations
2. **Optional**: Add monthly mode environment variables to your secret for explicit control
3. **Optional**: Update your monitoring/alerting to expect the new behavior

### **For New Deployments**

1. **Copy** the updated secret template: `deploy/overlays/example/secret.yaml.example`
2. **Configure** monthly mode variables if you need non-default behavior
3. **Deploy** using the updated manifests

## Monitoring and Troubleshooting

### **Expected Log Messages**

With monthly mode enabled, you'll see logs like:

```
Reading tab 'Monthly Report 2026-05' (gid=123456) from spreadsheet
Found 7 approved unprocessed projects for PoC (limited to 5 max)
```

### **Common Issues**

#### **Monthly Tab Not Found**
```
ValueError: No monthly report tab found for 2026-05
```

**Solution**: Ensure your Google Sheet has a tab named with one of these patterns:
- "Monthly Report 2026-05"
- "May 2026"  
- "Report-2026-05"
- "Monthly-2026-05"

#### **No Approved Projects**
```json
{
  "target_month": "2026-05",
  "projects_found": 0,
  "max_pocs": 5,
  "projects": []
}
```

**Solution**: Check that your monthly report tab has:
- GitHub repository URLs in the `link` column
- `pm_decision` = "approve" in the approval column
- Empty `poc_repo`, `poc_image`, and `poc_report` columns

### **Fallback to Legacy Mode**

If you need to quickly revert to the old behavior:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: legacy-mode-patch
data:
  AUTOPOC_MONTHLY_MODE: "false"
  MAX_EVALUATED_SHEETS: "4"
```

Apply this as an environment variable override to your cronjob.

## Related Documentation

- [Monthly Mode Usage Guide](./monthly-mode-usage.md)
- [Run-Sheet Skill Documentation](../.opencode/skills/run-sheet/SKILL.md)
- [Environment Variables Reference](../.env.example)