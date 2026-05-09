import os
from pathlib import Path

def test_skill_md_no_root_paths():
    """
    Assert that the contents of SKILL.md do not contain hardcoded host-layout paths
    such as /root/, ~/.openclaw/, or .openclaw/workspace/.
    """
    # Assuming tests are run from the project root or tests directory
    # Find SKILL.md relative to the project root
    project_root = Path(__file__).resolve().parent.parent
    skill_md_path = project_root / "SKILL.md"
    
    assert skill_md_path.exists(), f"SKILL.md not found at {skill_md_path}"
    
    content = skill_md_path.read_text(encoding="utf-8")
    
    # Check for forbidden strings
    forbidden_strings = [
        "/root/",
        "~/.openclaw/",
        ".openclaw/workspace/"
    ]
    
    for forbidden in forbidden_strings:
        assert forbidden not in content, f"SKILL.md contains forbidden hardcoded path: {forbidden}"
