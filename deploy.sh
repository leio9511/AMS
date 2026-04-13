#!/bin/bash
# ==========================================
# AMS AgentSkill Deployment Script
# ==========================================
set -e

PROJECT_DIR=$(dirname "$0")
cd "$PROJECT_DIR" || exit 1

SKILL_NAME="ams"
RUNTIME_DIR="$HOME/.openclaw/skills/$SKILL_NAME"
DATA_DIR="$HOME/.openclaw/data/$SKILL_NAME"

echo "Deploying $SKILL_NAME to $RUNTIME_DIR..."

# 1. Ensure the Prod/Dev isolation structure exists
mkdir -p "$RUNTIME_DIR/scripts"
mkdir -p "$DATA_DIR"

# 2. Copy SKILL.md and scripts
cp SKILL.md "$RUNTIME_DIR/SKILL.md"
cp -r scripts/* "$RUNTIME_DIR/scripts/"

# 3. Remotely deploy Windows bridge/ETL scripts via SSH to the QMT node
echo "Deploying Windows bridge/ETL scripts to QMT node..."
python3 deploy_to_windows.py

# 4. Execute the disaster recovery OpenClaw native cron registration
# Remove ALL existing jobs with the same name to prevent duplicates
EXISTING_JOB_IDS=$(openclaw cron list --json | jq -r '.jobs[] | select(.name == "ams_ledger_backup") | .id')
for JOB_ID in $EXISTING_JOB_IDS; do
    if [ -n "$JOB_ID" ]; then
        echo "Removing existing ams_ledger_backup cron job: $JOB_ID"
        openclaw cron rm "$JOB_ID"
    fi
done

echo "Registering backup_ledger cron job..."
openclaw cron add --name "ams_ledger_backup" --cron "0 1 * * *" --message "Execute \`python3 ~/.openclaw/skills/ams/scripts/backup_ledger.py\`. Parse the JSON output, summarize the backup status, and report the daily portfolio snapshot to this channel."

echo "✅ Skill deployed successfully. Run 'openclaw gateway restart' if it doesn't hot-reload."