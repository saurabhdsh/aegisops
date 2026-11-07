from __future__ import annotations

from aegisops.connectors.llm.openai import OpenAiNarrative
from aegisops.core.config import Settings


def build_narrative(settings: Settings) -> OpenAiNarrative | None:
    """Use a saved key in every mode. The ranker still decides the causes."""
    if not settings.openai_api_key or not settings.openai_model:
        return None
    if settings.openai_provider == "azure" and not settings.openai_base_url:
        return None
    return OpenAiNarrative(settings)
