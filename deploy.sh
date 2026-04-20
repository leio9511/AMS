#!/bin/bash
# ==========================================
# AMS AgentSkill Deployment Script
# ==========================================
set -e

PROJECT_DIR=$(dirname "$0")
cd "$PROJECT_DIR" || exit 1

SKILL_NAME="ams"
SRC_DIR="/root/projects/AMS"
DEST_SKILL_DIR="$HOME/.openclaw/skills/$SKILL_NAME"
DATA_DIR="$HOME/.openclaw/data/$SKILL_NAME"

echo "Deploying $SKILL_NAME to $DEST_SKILL_DIR..."

# 1. Ensure the Prod/Dev isolation structure exists
mkdir -p "$DEST_SKILL_DIR/scripts"
mkdir -p "$DEST_SKILL_DIR/ams"
mkdir -p "$DEST_SKILL_DIR/etl"
mkdir -p "$DATA_DIR"

# 2. Copy files using rsync
rsync -avh --delete "$SRC_DIR/ams/" "$DEST_SKILL_DIR/ams/"
rsync -avh --delete "$SRC_DIR/etl/" "$DEST_SKILL_DIR/etl/"
cp "$SRC_DIR/SKILL.md" "$DEST_SKILL_DIR/SKILL.md"
# Also copy remaining scripts just in case other things need them
rsync -avh --delete "$SRC_DIR/scripts/" "$DEST_SKILL_DIR/scripts/"

# 3. Remotely deploy Windows bridge/ETL scripts via SSH to the QMT node
echo "Deploying Windows bridge/ETL scripts to QMT node..."
python3 deploy_to_windows.py

# 4. Execute the disaster recovery OpenClaw native cron registration
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
