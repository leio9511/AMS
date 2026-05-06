from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_MANIFEST_PATH = Path("ignore_tests.json")
_ALLOWED_TOP_LEVEL_KEYS = {"pytest"}


def _parse_manifest_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)



def _validate_manifest_structure(manifest: Any) -> dict[str, list[str]]:
    if not isinstance(manifest, dict):
        raise ValueError("ignore_tests.json must contain a top-level JSON object")
    if set(manifest.keys()) != _ALLOWED_TOP_LEVEL_KEYS:
        raise ValueError("ignore_tests.json must contain only the 'pytest' top-level key")

    pytest_entries = manifest.get("pytest")
    if not isinstance(pytest_entries, list):
        raise ValueError("ignore_tests.json 'pytest' value must be a list")
    if not all(isinstance(entry, str) for entry in pytest_entries):
        raise ValueError("ignore_tests.json 'pytest' entries must all be strings")

    return {"pytest": pytest_entries}



def load_manifest(manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = _parse_manifest_json(path)
    return _validate_manifest_structure(manifest)



def _validate_pytest_entry(entry: str, repo_root: Path, seen: set[str]) -> None:
    if entry in seen:
        raise ValueError(f"Duplicate pytest ignore entry is invalid: {entry}")
    seen.add(entry)

    if any(token in entry for token in ("*", "?", "[", "]")):
        raise ValueError(f"Glob pytest ignore entry is invalid: {entry}")
    if "::" in entry:
        raise ValueError(f"Non-file pytest selector is invalid: {entry}")

    path = PurePosixPath(entry)
    if path.is_absolute():
        raise ValueError(f"Absolute pytest ignore entry is invalid: {entry}")
    if ".." in path.parts:
        raise ValueError(f"Parent-traversing pytest ignore entry is invalid: {entry}")
    if not path.parts or path.parts[0] != "tests":
        raise ValueError(f"Pytest ignore entry must live under tests/: {entry}")
    if path.suffix != ".py":
        raise ValueError(f"Pytest ignore entry must target a .py test file: {entry}")

    file_path = repo_root / Path(path)
    if not file_path.exists():
        raise ValueError(f"Pytest ignore entry does not exist: {entry}")
    if not file_path.is_file():
        raise ValueError(f"Pytest ignore entry must point to a file: {entry}")



def build_pytest_ignore_args(manifest: dict[str, Any], repo_root: str | Path = ".") -> list[str]:
    repo_root_path = Path(repo_root).resolve()
    pytest_entries = manifest["pytest"]
    seen: set[str] = set()

    for entry in pytest_entries:
        _validate_pytest_entry(entry, repo_root_path, seen)

    return [f"--ignore={entry}" for entry in pytest_entries]



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate ignore_tests.json and emit pytest --ignore arguments."
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args(argv)



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        ignore_args = build_pytest_ignore_args(manifest, args.repo_root)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    if ignore_args:
        print("\n".join(ignore_args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
