from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for the lab."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load environment variables, ensure directory setup, and return a LabConfig."""
    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()

    # Load environment variables if .env exists
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    data_dir = root / "data"
    state_dir = root / "state"
    profiles_dir = state_dir / "profiles"

    # Automatically ensure state/ and state/profiles/ exist
    state_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    provider_name = normalize_provider(os.getenv("LLM_PROVIDER", "openai"))
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))

    def _resolve_api_key(prov: str) -> str | None:
        p = normalize_provider(prov)
        if p == "gemini":
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if p == "openrouter":
            return os.getenv("OPENROUTER_API_KEY")
        if p == "openai":
            return os.getenv("OPENAI_API_KEY")
        if p == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY")
        if p == "custom":
            return os.getenv("CUSTOM_API_KEY") or os.getenv("OPENAI_API_KEY")
        return (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("CUSTOM_API_KEY")
        )

    base_url = os.getenv("CUSTOM_BASE_URL") or os.getenv("OLLAMA_BASE_URL")

    model_config = ProviderConfig(
        provider=provider_name,
        model_name=model_name,
        temperature=temperature,
        api_key=_resolve_api_key(provider_name),
        base_url=base_url,
    )

    judge_provider = normalize_provider(os.getenv("JUDGE_PROVIDER", provider_name))
    judge_model_name = os.getenv("JUDGE_MODEL", model_name)
    judge_model_config = ProviderConfig(
        provider=judge_provider,
        model_name=judge_model_name,
        temperature=0.0,
        api_key=_resolve_api_key(judge_provider),
        base_url=base_url,
    )

    compact_threshold = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "400"))
    compact_keep = int(os.getenv("COMPACT_KEEP_MESSAGES", "4"))

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=compact_threshold,
        compact_keep_messages=compact_keep,
        model=model_config,
        judge_model=judge_model_config,
    )
