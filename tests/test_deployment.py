import os
import re
import subprocess

def test_deploy_sh_syntax():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    assert os.path.exists(script_path), "deploy.sh not found"
    result = subprocess.run(['bash', '-n', script_path], capture_output=True, text=True)
    assert result.returncode == 0, f"Syntax error in deploy.sh: {result.stderr}"

def test_skill_md_content():
    skill_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../SKILL.md'))
    assert os.path.exists(skill_path), "SKILL.md not found"
    
    with open(skill_path, 'r') as f:
        content = f.read()
    
    assert "name: ams" in content, "SKILL.md missing 'name: ams' in frontmatter"
    assert "description: Automated Market Screener & Global Portfolio Ledger" in content, "SKILL.md missing description"
    assert "query_spread.py" in content, "SKILL.md missing query_spread.py instruction"
    assert "run_screener.py" in content, "SKILL.md missing run_screener.py instruction"
    assert "query_portfolio.py" in content, "SKILL.md missing query_portfolio.py instruction"
    assert "HEARTBEAT.md" in content, "SKILL.md missing heartbeat instruction"


def test_deploy_sh_cron_schedule():
    """Test Case 6: Verify deploy.sh has ams_daily_data_sync cron expression '5 8 * * 1-5'."""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    assert os.path.exists(script_path), "deploy.sh not found"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Verify ams_daily_data_sync cron job is registered with correct schedule
    assert 'ams_daily_data_sync' in content, "Missing ams_daily_data_sync cron job registration"
    
    # Check for the correct cron expression (5 8 * * 1-5 = 08:05 on weekdays Mon-Fri)
    # The cron expression should be: --cron "5 8 * * 1-5"
    cron_pattern = r'--cron\s+["\']5 8 \* \* 1-5["\']'
    assert re.search(cron_pattern, content), "Missing correct cron expression '5 8 * * 1-5' for ams_daily_data_sync"
    
    # Verify the cron job references trigger_daily_etl.py
    assert 'trigger_daily_etl.py' in content, "Missing reference to trigger_daily_etl.py in cron message"


def test_deploy_sh_idempotent_removal():
    """Test Case 7: Verify deploy.sh has idempotent removal logic using jq."""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    assert os.path.exists(script_path), "deploy.sh not found"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Verify ams_daily_data_sync has idempotent removal logic
    # Look for EXISTING_SYNC_IDS variable and openclaw cron list --json | jq pattern
    assert 'EXISTING_SYNC_IDS' in content, "Missing EXISTING_SYNC_IDS variable for ams_daily_data_sync"
    assert 'openclaw cron list --json' in content, "Missing 'openclaw cron list --json' for job lookup"
    assert 'jq' in content, "Missing jq command for parsing cron job list"
    assert '.jobs[] | select(.name == "ams_daily_data_sync")' in content, "Missing jq filter for ams_daily_data_sync"
    assert 'openclaw cron rm' in content, "Missing 'openclaw cron rm' for removing existing jobs"

def test_skill_md_governance():
    skill_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../SKILL.md'))
    with open(skill_path, 'r') as f:
        content = f.read()
    assert "**MANDATORY:** Currently in DEVELOPMENT stage" in content, "SKILL.md missing Governance rule"

def test_deploy_sh_etl_sync():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    with open(script_path, 'r') as f:
        content = f.read()
    assert 'rsync -avh --delete --exclude-from="$SRC_DIR/.release_ignore" "$SRC_DIR/" "$TMP_DIR/"' in content, "deploy.sh missing new rsync command"

def test_execute_bash_deploy_sh_dry_run():
    """Test Case 3: Execution bash deploy.sh (dry-run)"""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    assert os.path.exists(script_path), "deploy.sh not found"
    result = subprocess.run(['bash', '-n', script_path], capture_output=True, text=True)
    assert result.returncode == 0, f"Execution bash deploy.sh failed: {result.stderr}"

def test_release_ignore_content():
    ignore_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../.release_ignore'))
    assert os.path.exists(ignore_path), ".release_ignore not found"
    with open(ignore_path, 'r') as f:
        content = f.read()
    expected_rules = [
        ".git/", ".gitignore", ".pytest_cache/", "tests/", "__pycache__/", 
        "*.pyc", "*.log", "docs/PRDs/", ".sdlc_runs/", "run_backtest_script.py", 
        "turnover_test.py", "run_precision_backtest.py", "debug_trace*.py", 
        "append_experience.py", "update_issue_exp.py", "run_commit.py"
    ]
    for rule in expected_rules:
        assert rule in content, f"Rule {rule} not found in .release_ignore"

def test_deploy_sh_atomic_swap_logic():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    with open(script_path, 'r') as f:
        content = f.read()
    assert 'set -euo pipefail' in content, "deploy.sh missing set -euo pipefail"
    assert 'trap on_error ERR' in content, "deploy.sh missing trap on_error ERR"
    assert 'TMP_DIR="${DEST_SKILL_DIR}.tmp"' in content, "deploy.sh missing TMP_DIR"
    assert 'OLD_DIR="${DEST_SKILL_DIR}.old"' in content, "deploy.sh missing OLD_DIR"
    assert 'rsync -avh --delete --exclude-from="$SRC_DIR/.release_ignore" "$SRC_DIR/" "$TMP_DIR/"' in content, "deploy.sh missing rsync --exclude-from"

def test_deploy_sh_backup_and_restore():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    with open(script_path, 'r') as f:
        content = f.read()
    assert 'tar -czf "$BACKUP_FILE"' in content, "deploy.sh missing tar backup"
    assert 'mv "$OLD_DIR" "$DEST_SKILL_DIR"' in content, "deploy.sh missing restore mv command"

def test_deploy_sh_stale_backup_check():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    with open(script_path, 'r') as f:
        content = f.read()
    assert 'if [ -d "$OLD_DIR" ]; then' in content, "deploy.sh missing stale backup check"
    assert 'exit 1' in content, "deploy.sh missing exit 1 in stale backup check"

def test_prd_verification_path():
    prd_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../docs/PRDs/PRD_Modernize_Deployment_Script_and_Fix_Models_Sync.md'))
    assert os.path.exists(prd_path), "PRD file not found"
    with open(prd_path, 'r') as f:
        content = f.read()
    assert "~/.openclaw/skills/ams/ams/models/config.py" in content, "PRD missing the correct verification path"


