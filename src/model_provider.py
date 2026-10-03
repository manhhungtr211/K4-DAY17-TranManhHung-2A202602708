from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Provider configuration shared by the agents."""

    provider: str
    model_name: str
    temperature: float = 0.0
    api_key: str | None = None
    base_url: str | None = None


def normalize_provider(value: str) -> str:
    """Map aliases and normalize provider names."""
    val = (value or "").strip().lower()
    alias_map = {
        "openai": "openai",
        "gpt": "openai",
        "custom": "custom",
        "gemini": "gemini",
        "google": "gemini",
        "google-genai": "gemini",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "anthorpic": "anthropic",
        "ollama": "ollama",
        "openrouter": "openrouter",
    }
    return alias_map.get(val, val)


def build_chat_model(config: ProviderConfig):
    """Instantiate the chat model for the selected provider."""
    provider = normalize_provider(config.provider)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=config.api_key,
        )

    if provider == "custom":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=config.api_key or "EMPTY",
            base_url=config.base_url,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model_name,
            temperature=config.temperature,
            google_api_key=config.api_key,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.model_name,
            temperature=config.temperature,
            api_key=config.api_key,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.model_name,
            temperature=config.temperature,
            base_url=config.base_url or "http://localhost:11434",
        )

    if provider == "openrouter":
        try:
            from langchain_openrouter import ChatOpenRouter

            return ChatOpenRouter(
                model=config.model_name,
                temperature=config.temperature,
                api_key=config.api_key,
            )
        except ImportError:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=config.model_name,
                temperature=config.temperature,
                api_key=config.api_key,
                base_url="https://openrouter.ai/api/v1",
            )

    raise ValueError(f"Unsupported provider: {config.provider}")
