import os
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
