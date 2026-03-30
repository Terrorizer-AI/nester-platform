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


# ── Role → Model mapping ─────────────────────────────────────────────────────

ROLE_RESEARCH = "research"
ROLE_SYNTHESIS = "synthesis"
ROLE_EMAIL = "email"

_MODEL_REGISTRY: dict[str, ModelConfig] = {}


def _build_registry() -> dict[str, ModelConfig]:
    settings = get_settings()
    return {
        ROLE_RESEARCH: ModelConfig(
            model_id=settings.openai_research_model,
            temperature=0.1,
            max_tokens=8192,
            description="Thorough extraction, tool calling, deep analysis",
        ),
        ROLE_SYNTHESIS: ModelConfig(
            model_id=settings.openai_synthesis_model,
            temperature=0.7,
            max_tokens=8192,
            description="Creative reasoning, report generation, persona building",
        ),
        ROLE_EMAIL: ModelConfig(
            model_id=settings.openai_email_model,
            temperature=0.8,
            max_tokens=4096,
            description="Hyper-personalized email writing using full research context",
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
