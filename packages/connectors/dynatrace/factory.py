from __future__ import annotations

from aegisops.connectors.dynatrace.http import DynatraceHttp
from aegisops.connectors.dynatrace.simulator import DynatraceSimulator
from aegisops.core.config import Settings
from aegisops.core.exceptions import IntegrationError
from aegisops.runtime.connections import dynatrace_ready


def build_dynatrace(settings: Settings) -> DynatraceHttp | DynatraceSimulator:
    if dynatrace_ready(settings):
        return DynatraceHttp(settings)
    if settings.execution_mode == "SIMULATOR":
        return DynatraceSimulator()
    raise IntegrationError("Dynatrace is not configured for this execution mode")
