from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from aegisops.connectors.ansible.runner import RestrictedRunner, load_playbook
from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError, IntegrationError


class AutomationAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = RestrictedRunner()
        self.root = Path(settings.ansible_runbook_path)
        if not self.root.is_absolute():
            self.root = Path(__file__).resolve().parents[3] / self.root

    def load(self, slug: str) -> dict:
        manifest_path = self._manifest(slug)
        playbook = manifest_path.parent / "playbook.yml"
        load_playbook(playbook)
        checksum = hashlib.sha256(playbook.read_bytes()).hexdigest()
        import json

        manifest = json.loads(manifest_path.read_text())
        manifest["checksum"] = checksum
        manifest["path"] = str(playbook)
        return manifest

    def precheck(self, slug: str, *, parameters: dict, sandbox: Path) -> dict:
        manifest = self.load(slug)
        self._check_parameters(manifest, parameters)
        if self.settings.execution_mode == "LIVE":
            return {"passed": True, "summary": "parameters and module allowlist accepted", "checksum": manifest["checksum"], "log": []}
        result = self.runner.execute(
            Path(manifest["path"]),
            sandbox=sandbox,
            variables={key: str(value) for key, value in parameters.items()},
            action="precheck",
        )
        log = result.get("log") or []
        summary = "; ".join(log) if log else "parameters and module allowlist accepted"
        return {"passed": True, "summary": summary, "checksum": manifest["checksum"], "log": log}

    def execute(self, slug: str, *, parameters: dict, sandbox: Path, action: str = "execute") -> dict:
        if self.settings.execution_mode == "LIVE":
            raise IntegrationError(
                "LIVE execution requires an isolated automation endpoint. The local runner is not used for LIVE mode."
            )
        if self.settings.execution_mode == "SANDBOX" and parameters.get("environment") == "production":
            raise ForbiddenError("SANDBOX mode cannot target a production configuration item")
        manifest = self.load(slug)
        self._check_parameters(manifest, parameters)
        playbook = Path(manifest["path"])
        if self.settings.ansible_use_cli and self.settings.execution_mode != "SIMULATOR":
            if shutil.which("ansible-playbook") is None:
                raise IntegrationError("ansible-playbook is not installed")
            raise IntegrationError("CLI execution is disabled until an inventory scoped to this target is configured")
        result = self.runner.execute(playbook, sandbox=sandbox, variables={k: str(v) for k, v in parameters.items()}, action=action)
        result["checksum"] = manifest["checksum"]
        result["runbook"] = slug
        return result

    def verify(self, sandbox: Path, marker: str) -> dict:
        path = sandbox / marker
        return {"passed": path.exists(), "summary": f"marker {marker} exists={path.exists()}"}

    def _manifest(self, slug: str) -> Path:
        matches = list(self.root.glob(f"**/{slug}/manifest.json"))
        if len(matches) != 1:
            raise IntegrationError("Runbook manifest was not found", {"slug": slug})
        return matches[0]

    def _check_parameters(self, manifest: dict, parameters: dict) -> None:
        schema = manifest.get("parameters") or {}
        for name, rules in schema.items():
            if name not in parameters:
                raise ForbiddenError(f"Missing runbook parameter {name}")
            allowed = rules.get("enum")
            if allowed and parameters[name] not in allowed:
                raise ForbiddenError(f"Parameter {name} is outside the allowlist")
            minimum = rules.get("minimum")
            if minimum is not None and float(parameters[name]) < float(minimum):
                raise ForbiddenError(f"Parameter {name} is below the minimum")
