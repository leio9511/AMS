#!/bin/bash
cd /root/.openclaw/workspace/AMS/scripts
python3 weekly_audit.py

TODAY=$(date +%Y%m%d)
REPORT_FILE="../reports/weekly_audit_${TODAY}.md"

if [ -f "$REPORT_FILE" ]; then
    openclaw message send --target telegram --message "$(cat $REPORT_FILE)"
fi
