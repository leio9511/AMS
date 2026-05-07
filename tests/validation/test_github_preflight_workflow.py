from pathlib import Path
import ast
import re


WORKFLOW_PATH = Path(".github/workflows/preflight.yml")
WORKFLOW_DIR = WORKFLOW_PATH.parent
THIS_TEST_FILE = Path(__file__)


def _workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file at {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_preflight_workflow_exists_at_required_path():
    workflow_files = sorted(path.name for path in WORKFLOW_DIR.glob("*.y*ml"))
    assert WORKFLOW_PATH.exists(), f"Expected workflow at {WORKFLOW_PATH}"
    assert workflow_files == ["preflight.yml"], (
        "This slice should introduce only the required preflight workflow file "
        f"under {WORKFLOW_DIR}, found: {workflow_files}"
    )



def test_preflight_workflow_declares_push_and_pull_request_triggers():
    text = _workflow_text()
    on_block = re.search(r"(?ms)^on:\s*\n(?P<block>(?:^[ \t]+.*\n?)*)", text)

    assert on_block, "Workflow must declare an 'on' block"
    block = on_block.group("block")
    assert re.search(r"(?m)^[ \t]+push:\s*$", block), "Workflow must trigger on push"
    assert re.search(r"(?m)^[ \t]+pull_request:\s*$", block), "Workflow must trigger on pull_request"



def test_preflight_workflow_bootstraps_validated_requirements_test_baseline():
    text = _workflow_text()
    pip_install_lines = re.findall(r"(?m)^[ \t]+run:\s+(pip install[^\n]*)\s*$", text)

    assert "actions/setup-python" in text, "Workflow must set up a Python runtime"
    assert re.search(
        r"(?m)^[ \t]+run:\s+pip install -r requirements-test\.txt\s*$",
        text,
    ), "Workflow must install requirements-test.txt with the exact validated command"
    assert pip_install_lines == ["pip install -r requirements-test.txt"], (
        "Workflow must bootstrap dependencies from requirements-test.txt only, "
        f"found pip install commands: {pip_install_lines}"
    )



def test_preflight_workflow_runs_exact_repository_gate_command():
    text = _workflow_text()
    run_lines = re.findall(r"(?m)^[ \t]+run:\s+([^\n]+)\s*$", text)

    assert "bash preflight.sh" in run_lines, "Workflow must run the exact repository gate command"
    assert re.search(r"(?m)^[ \t]+run:\s+bash preflight\.sh\s*$", text), (
        "Workflow must invoke the exact command 'bash preflight.sh'"
    )
    assert not any("pytest" in line for line in run_lines), (
        "Workflow must not replace preflight.sh with a decomposed pytest command chain"
    )



def test_preflight_workflow_preserves_truthful_failure_semantics_without_masking():
    text = _workflow_text()
    forbidden_tokens = [
        "continue-on-error",
        "|| true",
        "; true",
        "exit 0",
    ]

    for token in forbidden_tokens:
        assert token not in text, f"Workflow must not contain masking token: {token}"



def test_preflight_workflow_is_a_local_contract_check_only():
    source = THIS_TEST_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    subprocess_run_calls = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ):
            subprocess_run_calls += 1

    assert str(WORKFLOW_PATH) in source, "Tests must inspect the committed local workflow file"
    assert subprocess_run_calls == 0, "Tests must not shell out to validate the workflow contract"
    assert all(module.split(".")[0] not in {"requests", "httpx", "socket", "urllib"} for module in imported_modules), (
        "Workflow contract tests must stay repo-local and avoid network-capable imports"
    )
