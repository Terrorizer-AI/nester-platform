"""
Model registry — maps agent roles to LLM model IDs.

Research agents (tool calling, extraction) → GPT-5.4-nano (400K ctx, strong reasoning)
Synthesis agents (reasoning, generation)  → GPT-5.4-nano (400K ctx, strong reasoning)
Email composer (hyper-personalized email)  → GPT-4o (best writing quality, full context)
"""

from dataclasses import dataclass

from config.settings import get_settings


@dataclass(frozen=True)
class ModelConfig:
    model_id: str
    temperature: float
    max_tokens: int
    description: str
    api_key: str = ""
    base_url: str = ""


# ── Role → Model mapping ─────────────────────────────────────────────────────

ROLE_RESEARCH = "research"
ROLE_SYNTHESIS = "synthesis"
ROLE_EMAIL = "email"

_MODEL_REGISTRY: dict[str, ModelConfig] = {}


def _resolve_llm_creds(settings, model_id: str) -> tuple[str, str]:
    """Return (api_key, base_url) based on whether the model is a DeepSeek model."""
    from config.keys import get_api_key

    if model_id.startswith("deepseek"):
        key = get_api_key("DEEPSEEK_API_KEY") or settings.deepseek_api_key
        return key, settings.deepseek_base_url
    key = get_api_key("OPENAI_API_KEY") or settings.openai_api_key
    return key, ""


def _build_registry() -> dict[str, ModelConfig]:
    settings = get_settings()

    r_key, r_url = _resolve_llm_creds(settings, settings.openai_research_model)
    s_key, s_url = _resolve_llm_creds(settings, settings.openai_synthesis_model)
    e_key, e_url = _resolve_llm_creds(settings, settings.openai_email_model)

    return {
        ROLE_RESEARCH: ModelConfig(
            model_id=settings.openai_research_model,
            temperature=0.1,
            max_tokens=8192,
            description="Thorough extraction, tool calling, deep analysis",
            api_key=r_key,
            base_url=r_url,
        ),
        ROLE_SYNTHESIS: ModelConfig(
            model_id=settings.openai_synthesis_model,
            temperature=0.7,
            max_tokens=8192,
            description="Creative reasoning, report generation, persona building",
            api_key=s_key,
            base_url=s_url,
        ),
        ROLE_EMAIL: ModelConfig(
            model_id=settings.openai_email_model,
            temperature=0.8,
            max_tokens=8192,
            description="Hyper-personalized email writing using full research context",
            api_key=e_key,
            base_url=e_url,
        ),
    }


def get_model(role: str) -> ModelConfig:
    """Return the ModelConfig for a given agent role."""
    global _MODEL_REGISTRY
    if not _MODEL_REGISTRY:
        _MODEL_REGISTRY = _build_registry()
    if role not in _MODEL_REGISTRY:
        raise ValueError(f"Unknown model role: {role!r}. Valid: {list(_MODEL_REGISTRY)}")
    return _MODEL_REGISTRY[role]


def get_model_id(role: str) -> str:
    """Shortcut: return just the model ID string for a role."""
    return get_model(role).model_id


def build_chat_llm(model_config: ModelConfig, **overrides):
    """Build a ChatOpenAI instance from a ModelConfig, routing to DeepSeek when needed."""
    from langchain_openai import ChatOpenAI

    kwargs = {
        "model": model_config.model_id,
        "temperature": overrides.get("temperature", model_config.temperature),
        "max_tokens": overrides.get("max_tokens", model_config.max_tokens),
    }
    if model_config.api_key:
        kwargs["api_key"] = model_config.api_key
    if model_config.base_url:
        kwargs["base_url"] = model_config.base_url
    return ChatOpenAI(**kwargs)
