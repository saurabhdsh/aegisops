"""Restricted runbook runner.

Playbooks may use only the modules listed below. Paths must stay inside the
per-execution sandbox. LIVE mode does not use this runner.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import yaml

from aegisops.core.exceptions import ForbiddenError, IntegrationError

ALLOWED_MODULES = frozenset(
    {
        "ansible.builtin.copy",
        "ansible.builtin.stat",
        "ansible.builtin.debug",
        "aegisops.safe.cleanup_aged_logs",
        "aegisops.safe.record_extension",
    }
)
_REJECTED = ("ansible.builtin.shell", "ansible.builtin.command", "ansible.builtin.raw", "ansible.builtin.script")


def load_playbook(path: Path) -> list[dict]:
    document = yaml.safe_load(path.read_text())
    plays = document if isinstance(document, list) else [document]
    tasks: list[dict] = []
    for play in plays:
        for task in play.get("tasks") or []:
            module = next((key for key in task if key not in {"name", "when"}), None)
            if module is None:
                raise ForbiddenError(f"Runbook task has no module: {task.get('name')}")
            if module in _REJECTED or module not in ALLOWED_MODULES:
                raise ForbiddenError(f"Runbook module is not allowlisted: {module}")
            tasks.append({"name": task.get("name", module), "module": module, "args": task[module], "when": task.get("when")})
    return tasks


def _inside(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    base = root.resolve()
    return resolved == base or str(resolved).startswith(str(base) + os.sep)


def _render(value: object, variables: dict[str, str]) -> str:
    text = str(value)
    for key, item in variables.items():
        text = text.replace("{{ " + key + " }}", item).replace("{{" + key + "}}", item)
    if "{{" in text:
        raise ForbiddenError("Runbook variable was not substituted")
    return text


class RestrictedRunner:
    def execute(self, playbook: Path, *, sandbox: Path, variables: dict[str, str], action: str) -> dict:
        sandbox.mkdir(parents=True, exist_ok=True)
        tasks = load_playbook(playbook)
        variables = {**variables, "sandbox_dir": str(sandbox)}
        log: list[str] = []
        deleted_bytes = 0
        for task in tasks:
            when = task.get("when")
            if when and _render(when, variables) != action:
                log.append(f"skip {task['name']}")
                continue
            module = task["module"]
            args = task["args"] or {}
            if module == "ansible.builtin.copy":
                dest = Path(_render(args["dest"], variables))
                if not _inside(dest, sandbox):
                    raise ForbiddenError("copy destination escapes the sandbox")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(_render(args.get("content", ""), variables))
                log.append(f"copy {dest.name}")
            elif module == "ansible.builtin.stat":
                target = Path(_render(args["path"], variables))
                if not _inside(target, sandbox):
                    raise ForbiddenError("stat path escapes the sandbox")
                log.append(f"stat {target.name} exists={target.exists()}")
            elif module == "ansible.builtin.debug":
                log.append(_render(args.get("msg", ""), variables))
            elif module == "aegisops.safe.cleanup_aged_logs":
                deleted_bytes += _cleanup(args, variables, sandbox, log)
            elif module == "aegisops.safe.record_extension":
                dest = Path(_render(args["dest"], variables))
                if not _inside(dest, sandbox):
                    raise ForbiddenError("extension record escapes the sandbox")
                dest.write_text(_render(args.get("content", "extended\n"), variables))
                log.append(f"record extension {dest.name}")
            else:
                raise ForbiddenError(f"Runbook module is not allowlisted: {module}")
        return {"log": log, "deleted_bytes": deleted_bytes, "sandbox": str(sandbox), "executor": "restricted-runbook-runner"}


def _cleanup(args: dict, variables: dict[str, str], sandbox: Path, log: list[str]) -> int:
    directory = Path(_render(args["directory"], variables))
    if not _inside(directory, sandbox):
        raise ForbiddenError("cleanup directory escapes the sandbox")
    min_age = int(float(_render(args["min_age_days"], variables)))
    if min_age < 7:
        raise ForbiddenError("Log cleanup cannot go below the seven-day retention floor")
    suffix = _render(args.get("name_suffix", ".log"), variables)
    if "/" in suffix or suffix.startswith("."):
        if suffix != ".log":
            raise ForbiddenError("cleanup suffix is not an approved log suffix")
    deleted = 0
    now = time.time()
    if not directory.exists():
        raise IntegrationError("cleanup directory does not exist")
    for entry in directory.iterdir():
        if not entry.is_file() or not entry.name.endswith(".log"):
            continue
        age_days = (now - entry.stat().st_mtime) / 86400
        if age_days >= min_age:
            deleted += entry.stat().st_size
            entry.unlink()
            log.append(f"delete {entry.name}")
    return deleted
