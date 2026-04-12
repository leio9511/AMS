# ISSUE-1110: Fix Duplicate Cron Job Registration in deploy.sh

## Problem
The `deploy.sh` script for AMS uses `openclaw cron add --name ams_ledger_backup ...` to register a disaster recovery cron job. However, the OpenClaw CLI generates a new UUID for each invocation, causing duplicate cron jobs to stack up every time a deployment is triggered.

## Requirements
Modify `deploy.sh` to prevent duplicate cron jobs.
Before adding the new cron job, the script must query the existing jobs, find any job with the name `ams_ledger_backup`, and remove it.
