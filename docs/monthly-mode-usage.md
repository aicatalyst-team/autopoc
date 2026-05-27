# Monthly Mode Usage Guide

This document describes how to use the new monthly mode functionality for processing Google Sheets.

## Overview

The monthly mode feature allows AutoPoC to:
1. **Read from monthly report tabs** instead of the last N tabs
2. **Automatically find** tabs with monthly naming patterns (e.g., "Monthly Report 2026-05", "May 2026", etc.)
3. **Process approved projects** that haven't had PoCs run yet
4. **Configure the maximum number** of PoCs to run per batch (up to 5 by default)

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Enable monthly mode
AUTOPOC_MONTHLY_MODE=true

# Target month (optional - defaults to current month)
AUTOPOC_TARGET_MONTH=2026-05

# Maximum number of PoCs to run from monthly report
MAX_MONTHLY_POCS=5
```

### Configuration Values

In `AutoPoCConfig`:

```python
monthly_mode: bool = Field(
    default=False,
    validation_alias="AUTOPOC_MONTHLY_MODE",
    description="If True, read from monthly report tab instead of last N tabs",
)
target_month: str | None = Field(
    default=None,
    validation_alias="AUTOPOC_TARGET_MONTH", 
    description="Target month for monthly mode in YYYY-MM format (defaults to current month)",
)
max_monthly_pocs: int = Field(
    default=5,
    description="Maximum number of PoCs to run from monthly report (when monthly_mode=True)",
)
```

## CLI Usage

### Reading from Monthly Report Tabs

```bash
# Read from current month's report tab
python -m autopoc.cli_tools sheet-reader \
  --sheet-id "$AUTOPOC_SHEET_ID" \
  --credentials "$AUTOPOC_SHEET_CREDENTIALS" \
  --monthly-mode

# Read from specific month's report tab  
python -m autopoc.cli_tools sheet-reader \
  --sheet-id "$AUTOPOC_SHEET_ID" \
  --credentials "$AUTOPOC_SHEET_CREDENTIALS" \
  --monthly-mode \
  --target-month "2026-05"
```

### Finding Approved Unprocessed Projects

```bash
# Find up to 5 approved projects that need PoCs
python -m autopoc.cli_tools monthly-pocs \
  --sheet-id "$AUTOPOC_SHEET_ID" \
  --credentials "$AUTOPOC_SHEET_CREDENTIALS" \
  --max-pocs 5

# Find projects from a specific month
python -m autopoc.cli_tools monthly-pocs \
  --sheet-id "$AUTOPOC_SHEET_ID" \
  --credentials "$AUTOPOC_SHEET_CREDENTIALS" \
  --target-month "2026-05" \
  --max-pocs 3
```

## Monthly Tab Naming Patterns

The system recognizes these tab naming patterns:

### Exact Matches
- `Monthly Report YYYY-MM` (e.g., "Monthly Report 2026-05")  
- `Monthly-YYYY-MM` (e.g., "Monthly-2026-05")
- `Report-YYYY-MM` (e.g., "Report-2026-05")
- `YYYY-MM Monthly Report` (e.g., "2026-05 Monthly Report")
- `YYYY-MM-Monthly` (e.g., "2026-05-Monthly")
- `YYYY-MM Report` (e.g., "2026-05 Report")

### Month Name Patterns  
- `Monthly Report Month Year` (e.g., "Monthly Report May 2026")
- `Report Month Year` (e.g., "Report May 2026")
- `Month Year` (e.g., "May 2026")

All matching is **case-insensitive**.

## Run-Sheet Skill Integration

When using the `run-sheet` skill with monthly mode:

```bash
# Set environment variables
export AUTOPOC_MONTHLY_MODE=true
export AUTOPOC_TARGET_MONTH=2026-05
export MAX_MONTHLY_POCS=5

# Run the skill (will automatically use monthly mode)
```

The skill will:
1. **Look for the monthly report tab** instead of reading the last N tabs
2. **Find approved unprocessed projects** from that tab
3. **Run up to MAX_MONTHLY_POCS PoCs** (default 5) instead of MAX_BATCHED_POC (default 2)
4. **Write results back** to the monthly report tab

## Project Selection Logic

In monthly mode, the system:

1. **Reads from monthly report tab** (instead of last N tabs)
2. **Applies standard filters**:
   - Must be GitHub repositories
   - Must have `pm_decision` = "approve" 
   - Must not already have PoC results
3. **Limits to max_monthly_pocs** (configurable, default 5)
4. **Runs PoCs sequentially** to avoid resource contention

## Error Handling

### Tab Not Found
If the monthly report tab is not found:
```
ValueError: No monthly report tab found for 2026-05
```

Available tab names are logged for debugging.

### No Approved Projects
If no approved unprocessed projects are found:
```json
{
  "target_month": "2026-05", 
  "projects_found": 0,
  "max_pocs": 5,
  "projects": []
}
```

## Backward Compatibility

The new monthly mode is **fully backward compatible**:

- When `monthly_mode=False` (default), behavior is unchanged
- All existing CLI commands and environment variables continue to work
- The `max_tabs` parameter is ignored when `monthly_mode=True`
- Standard mode still processes the last N tabs as before

## Example Workflow

```bash
# 1. Check what approved projects need PoCs
python -m autopoc.cli_tools monthly-pocs \
  --sheet-id "your-sheet-id" \
  --credentials "/path/to/credentials.json" \
  --target-month "2026-05"

# 2. If projects found, run the PoCs using run-sheet skill
export AUTOPOC_MONTHLY_MODE=true
export AUTOPOC_TARGET_MONTH=2026-05  
export MAX_MONTHLY_POCS=3

# Use run-sheet skill which will automatically use monthly mode
```