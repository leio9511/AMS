#!/bin/bash
# ==========================================
# AMS AgentSkill Deployment Script
# ==========================================
set -euo pipefail

PROJECT_DIR=$(dirname "$0")
cd "$PROJECT_DIR" || exit 1

SKILL_NAME="ams"
SRC_DIR="/root/projects/AMS"
DEST_SKILL_DIR="$HOME/.openclaw/skills/$SKILL_NAME"
DATA_DIR="$HOME/.openclaw/data/$SKILL_NAME"
BACKUP_DIR="$HOME/.openclaw/skills"

echo "Deploying $SKILL_NAME to $DEST_SKILL_DIR..."

TMP_DIR="${DEST_SKILL_DIR}.tmp"
OLD_DIR="${DEST_SKILL_DIR}.old"

on_error() {
    echo "CRITICAL: Deployment failed. Initiating automated recovery..."
    if [ ! -d "$DEST_SKILL_DIR" ] && [ -d "$OLD_DIR" ]; then
        mv "$OLD_DIR" "$DEST_SKILL_DIR"
        echo "RESTORED: Production directory recovered from backup."
    fi
}
trap on_error ERR

# 1. Validation
if [ -d "$OLD_DIR" ]; then
    echo "FATAL: Stale backup directory found at $OLD_DIR. Recover manually."
    exit 1
fi

# 2. Staging
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
rsync -avh --delete --exclude-from="$SRC_DIR/.release_ignore" "$SRC_DIR/" "$TMP_DIR/"

# 3. Swap and Backup
if [ -d "$DEST_SKILL_DIR" ]; then
    BACKUP_FILE="${BACKUP_DIR}/ams_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    tar -czf "$BACKUP_FILE" -C "$(dirname "$DEST_SKILL_DIR")" "$(basename "$DEST_SKILL_DIR")"
    mv "$DEST_SKILL_DIR" "$OLD_DIR"
fi

mv "$TMP_DIR" "$DEST_SKILL_DIR"
rm -rf "$OLD_DIR"

# 4. Ensure Data directory exists
mkdir -p "$DATA_DIR"

# 5. Remotely deploy Windows bridge/ETL scripts via SSH to the QMT node
echo "Deploying Windows bridge/ETL scripts to QMT node..."
python3 deploy_to_windows.py

# 6. Execute the disaster recovery OpenClaw native cron registration
# Remove ALL existing jobs with the same name to prevent duplicates
EXISTING_JOB_IDS=$(openclaw cron list --json | jq -r '.jobs[] | select(.name == "ams_ledger_backup") | .id' || echo "")
for JOB_ID in $EXISTING_JOB_IDS; do
    if [ -n "$JOB_ID" ]; then
        echo "Removing existing ams_ledger_backup cron job: $JOB_ID"
        openclaw cron rm "$JOB_ID" || true
    fi
done

echo "Registering backup_ledger cron job..."
openclaw cron add --name "ams_ledger_backup" --cron "0 1 * * *" --message "Execute \`python3 ~/.openclaw/skills/ams/scripts/backup_ledger.py\`. Parse the JSON output, summarize the backup status, and report the daily portfolio snapshot to this channel." || true

# Register daily data sync & ETL cron job
EXISTING_SYNC_IDS=$(openclaw cron list --json | jq -r '.jobs[] | select(.name == "ams_daily_data_sync") | .id' || echo "")
for JOB_ID in $EXISTING_SYNC_IDS; do
    if [ -n "$JOB_ID" ]; then
        echo "Removing existing ams_daily_data_sync cron job: $JOB_ID"
        openclaw cron rm "$JOB_ID" || true
    fi
done

echo "Registering ams_daily_data_sync cron job..."
openclaw cron add --name "ams_daily_data_sync" --cron "5 8 * * 1-5" --message "Execute \`python3 ~/.openclaw/skills/ams/etl/trigger_daily_etl.py\`. Parse the JSON output and report the data sync status to the Boss." || true

echo "✅ Skill deployed successfully. Run 'openclaw gateway restart' if it doesn't hot-reload."
