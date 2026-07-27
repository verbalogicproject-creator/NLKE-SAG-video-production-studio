#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = {"run_id", "task_id", "objective", "acceptance_criteria", "assigned_role", "task", "write_scope", "verification", "budget", "instruction_hash"}
MODELS = {"sol": "gpt-5.6-sol", "terra": "gpt-5.6-terra", "luna": "gpt-5.6-luna"}


def canonical_hash(task: dict) -> str:
    payload = {key: value for key, value in task.items() if key != "instruction_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(task: dict, available_models: set[str]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - set(task))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    role = task.get("assigned_role")
    if role not in MODELS:
        errors.append("assigned_role must be sol, terra, or luna")
    if not task.get("acceptance_criteria") or not task.get("verification"):
        errors.append("acceptance_criteria and verification must not be empty")
    if role == "luna" and task.get("write_scope"):
        errors.append("Luna tasks must have an empty write_scope")
    budget = task.get("budget") or {}
    if budget.get("max_attempts") not in {1, 2} or budget.get("max_children") != 0:
        errors.append("budget requires max_attempts 1..2 and max_children 0")
    if task.get("instruction_hash") != canonical_hash(task):
        errors.append("instruction_hash does not match the canonical envelope")
    if available_models and MODELS.get(role) not in available_models:
        errors.append(f"configured model is unavailable: {MODELS.get(role)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", type=Path)
    parser.add_argument("--available-model", action="append", default=[])
    parser.add_argument("--print-hash", action="store_true")
    args = parser.parse_args()
    task = json.loads(args.task.read_text(encoding="utf-8"))
    if args.print_hash:
        print(canonical_hash(task))
        return 0
    errors = validate(task, set(args.available_model))
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    print(f"OK: {task['task_id']} -> {task['assigned_role']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
