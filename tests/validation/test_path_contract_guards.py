from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_PATTERNS = [
    "/root/" + "projects/AMS",
    "/root/" + ".openclaw",
    ".openclaw/" + "workspace",
]

HIGH_VALUE_CONTRACT_SURFACES = [
    REPO_ROOT / "main_runner.py",
    REPO_ROOT / "ams" / "utils",
    REPO_ROOT / "ams" / "validators",
    REPO_ROOT / "etl",
    REPO_ROOT / "tests" / "conftest.py",
    REPO_ROOT / "tests" / "validation",
    REPO_ROOT / "tests" / "golden" / "data" / "metadata.json",
    REPO_ROOT / "tests" / "test_execution_semantics_priority.py",
    REPO_ROOT / "tests" / "test_execution_semantics_rebalance.py",
    REPO_ROOT / "tests" / "test_execution_semantics_stop_loss.py",
    REPO_ROOT / "tests" / "test_execution_semantics_take_profit.py",
    REPO_ROOT / "tests" / "test_execution_arbitration.py",
    REPO_ROOT / "tests" / "test_order_semantics_e2e.py",
    REPO_ROOT / "tests" / "test_main_runner_smoke.py",
]


def _iter_files(paths):
    for path in paths:
        if path.is_dir():
            yield from sorted(p for p in path.rglob("*") if p.is_file())
        elif path.exists():
            yield path


def _assert_no_forbidden_patterns(file_path: Path):
    content = file_path.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_PATTERNS:
        assert pattern not in content, f"Forbidden host-layout assumption '{pattern}' found in {file_path.relative_to(REPO_ROOT)}"


def test_validator_source_has_no_root_bound_default_literals():
    _assert_no_forbidden_patterns(REPO_ROOT / "ams" / "validators" / "cb_data_validator.py")


def test_backtest_path_surface_rejects_root_projects_and_openclaw_workspace_contracts():
    files_to_check = [
        REPO_ROOT / "docs" / "ROADMAP.md",
        REPO_ROOT / "docs" / "architecture" / "ARCHITECTURE.md",
    ]
    files_to_check.extend(list((REPO_ROOT / "tests" / "validation").glob("*.py")))

    for file_path in files_to_check:
        if file_path.exists():
            _assert_no_forbidden_patterns(file_path)


def test_etl_source_has_no_root_bound_default_literals():
    files_to_check = [
        REPO_ROOT / "etl" / "jqdata_sync_cb.py",
        REPO_ROOT / "etl" / "cb_etl_runner.py",
    ]

    for file_path in files_to_check:
        _assert_no_forbidden_patterns(file_path)


def test_high_value_runtime_and_validation_surfaces_have_no_host_layout_residue():
    for file_path in _iter_files(HIGH_VALUE_CONTRACT_SURFACES):
        if file_path.suffix in {".py", ".json"}:
            _assert_no_forbidden_patterns(file_path)


def test_architecture_docs_describe_mutable_data_as_configuration_controlled():
    architecture_path = REPO_ROOT / "docs" / "architecture" / "ARCHITECTURE.md"
    assert architecture_path.exists(), "ARCHITECTURE.md not found"

    content = architecture_path.read_text(encoding="utf-8")

    assert "Mutable research/backtest data" in content
    assert "configuration-controlled" in content
    assert "Explicitly resolved via CLI > ENV > AMS-owned config > project-local default" in content


def test_roadmap_docs_keep_phase2_gate_without_host_layout_canon():
    roadmap_path = REPO_ROOT / "docs" / "ROADMAP.md"
    assert roadmap_path.exists(), "ROADMAP.md not found"

    content = roadmap_path.read_text(encoding="utf-8")

    assert "ISSUE-1142 is a blocking issue for AMS Phase 2." in content
    assert ("/root/" + "projects/AMS/data/cb_history_factors.csv") not in content
    assert "without declaring a root-only machine path as the canonical contract" in content
