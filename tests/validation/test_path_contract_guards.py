import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def test_backtest_path_surface_rejects_root_projects_and_openclaw_workspace_contracts():
    # Obfuscate to prevent self-matching when scanning this file
    forbidden_patterns = [
        "/root/" + "projects/AMS",
        "/root/" + ".openclaw",
        ".openclaw/" + "workspace"
    ]
    
    files_to_check = [
        REPO_ROOT / "docs" / "ROADMAP.md",
        REPO_ROOT / "docs" / "architecture" / "ARCHITECTURE.md"
    ]
    # Add all validation test files
    files_to_check.extend(list((REPO_ROOT / "tests" / "validation").glob("*.py")))
    
    for file_path in files_to_check:
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert pattern not in content, f"Forbidden host-layout assumption '{pattern}' found in {file_path.relative_to(REPO_ROOT)}"

def test_architecture_docs_describe_mutable_data_as_configuration_controlled():
    architecture_path = REPO_ROOT / "docs" / "architecture" / "ARCHITECTURE.md"
    assert architecture_path.exists(), "ARCHITECTURE.md not found"
    
    content = architecture_path.read_text(encoding="utf-8")
    
    # Asserting that the document distinguishes mutable data and describes configuration semantics
    assert "Mutable research/backtest data" in content
    assert "configuration-controlled" in content
    assert "Explicitly resolved via CLI > ENV > AMS-owned config > project-local default" in content

def test_roadmap_docs_keep_phase2_gate_without_host_layout_canon():
    roadmap_path = REPO_ROOT / "docs" / "ROADMAP.md"
    assert roadmap_path.exists(), "ROADMAP.md not found"
    
    content = roadmap_path.read_text(encoding="utf-8")
    
    # Verify Phase 2 gate is still there
    assert "ISSUE-1142 is a blocking issue for AMS Phase 2." in content
    
    # Verify it doesn't use the old layout canon
    assert ("/root/" + "projects/AMS/data/cb_history_factors.csv") not in content
    assert "without declaring a root-only machine path as the canonical contract" in content
