"""LLM Configuration."""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class LLMConfig:
    """LLM configuration settings."""

    # Primary model (Gemini via LiteLLM)
    model: str = "gemini/gemini-2.0-flash"

    # Model aliases for different use cases
    fast_model: str = "gemini/gemini-2.0-flash"  # Quick responses
    smart_model: str = "gemini/gemini-1.5-pro"  # Complex tasks

    # API settings
    timeout: float = 30.0
    max_retries: int = 2

    # Generation defaults
    temperature: float = 0.7
    max_tokens: int = 4096

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables."""
        return cls(
            model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
            fast_model=os.getenv("LLM_FAST_MODEL", "gemini/gemini-2.0-flash"),
            smart_model=os.getenv("LLM_SMART_MODEL", "gemini/gemini-1.5-pro"),
            timeout=float(os.getenv("LLM_TIMEOUT", "30.0")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        )


@lru_cache
def get_llm_config() -> LLMConfig:
    """Get cached LLM configuration."""
    return LLMConfig.from_env()


# Model mapping for backwards compatibility with old model names
MODEL_MAPPING = {
    # Old Claude model names -> Gemini equivalents
    "haiku": "gemini/gemini-2.0-flash",
    "sonnet": "gemini/gemini-1.5-pro",
    "opus": "gemini/gemini-1.5-pro",  # No direct equivalent, use Pro
    # Full model IDs
    "claude-haiku-4-5-20251001": "gemini/gemini-2.0-flash",
    "claude-sonnet-4-5-20250929": "gemini/gemini-1.5-pro",
    "claude-opus-4-5-20251101": "gemini/gemini-1.5-pro",
}


def get_model_for_task(task: str = "default") -> str:
    """Get appropriate model for a specific task.

    Args:
        task: Task type - "fast", "smart", "quiz", "title", "chat"

    Returns:
        Model identifier string
    """
    config = get_llm_config()

    task_models = {
        "fast": config.fast_model,
        "smart": config.smart_model,
        "quiz": config.fast_model,  # Quiz generation - fast is fine
        "title": config.fast_model,  # Title generation - fast is fine
        "chat": config.model,  # Default chat model
        "default": config.model,
    }

    return task_models.get(task, config.model)


def translate_model_name(old_name: str) -> str:
    """Translate old Claude model names to Gemini equivalents.

    Args:
        old_name: Old model name (e.g., "haiku", "sonnet")

    Returns:
        Gemini model identifier
    """
    return MODEL_MAPPING.get(old_name.lower(), get_llm_config().model)
