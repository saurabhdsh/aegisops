from __future__ import annotations

from aegisops.connectors.servicenow.http import ServiceNowHttp
from aegisops.connectors.servicenow.simulator import ServiceNowSimulator
from aegisops.core.config import Settings
from aegisops.core.exceptions import IntegrationError
from aegisops.runtime.connections import servicenow_ready


def build_servicenow(settings: Settings) -> ServiceNowHttp | ServiceNowSimulator:
    if servicenow_ready(settings):
        return ServiceNowHttp(settings)
    if settings.execution_mode == "SIMULATOR":
        return ServiceNowSimulator()
    raise IntegrationError("ServiceNow is not configured for this execution mode")
