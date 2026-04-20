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
    assert 'rsync -avh --delete "$SRC_DIR/etl/" "$DEST_SKILL_DIR/etl/"' in content, "deploy.sh missing etl/ rsync"

def test_execute_bash_deploy_sh_dry_run():
    """Test Case 3: Execution bash deploy.sh (dry-run)"""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deploy.sh'))
    assert os.path.exists(script_path), "deploy.sh not found"
    result = subprocess.run(['bash', '-n', script_path], capture_output=True, text=True)
    assert result.returncode == 0, f"Execution bash deploy.sh failed: {result.stderr}"
