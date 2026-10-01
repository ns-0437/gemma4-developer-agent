"""Generation configuration resolution and validation."""

from __future__ import annotations

from typing import Any

from google.genai import types as genai_types

from ..context import CompilationContext
from ..schema import SandboxedLlmAgentConfig


def _get_genai_types(ctx: CompilationContext | None = None) -> Any:
    if ctx is not None and ctx.agent_factory and ctx.agent_factory.genai_types is not None:
        return ctx.agent_factory.genai_types
    return genai_types


def resolve_generation_config(
    config: SandboxedLlmAgentConfig,
    ctx: CompilationContext,
) -> Any:
    """Resolve and validate the LLM generation configuration against organizer constraints.

    Args:
        config: The sandboxed LLM agent configuration object.
        ctx: The compilation context containing organizer-defined generation constraints.

    Returns:
        A GenerateContentConfig instance if configuration or defaults exist, otherwise None.

    Raises:
        SubmissionValidationError: If the generation configuration violates organizer-defined constraints.
    """
    types_mod = _get_genai_types(ctx)
    if config.generate_content_config is not None:
        config_dict = config.generate_content_config.model_dump(exclude_none=True)

        if ctx.generation_constraints is not None:
            config_dict = ctx.generation_constraints.validate_config(
                config_dict, config.name
            )

        if config_dict:
            return types_mod.GenerateContentConfig(**config_dict)
        return None

    # No user config — apply organizer defaults if any
    if (
        ctx.generation_constraints is not None
        and ctx.generation_constraints.defaults
    ):
        validated = ctx.generation_constraints.validate_config({}, config.name)
        return types_mod.GenerateContentConfig(
            **validated
        )

    return None


def apply_thinking_config_to_model(model: Any, gen_config: Any) -> Any:
    """Attach thinking_config from GenerateContentConfig to LiteLlm._additional_args.

    Because ADK's LiteLlm._get_completion_inputs() does not forward Google GenAI
    thinking_config to OpenAI-compatible endpoints (like vLLM), this bridges
    thinking_level and include_thoughts into extra_body.chat_template_kwargs.enable_thinking
    and reasoning_effort on a cloned model instance.
    """
    if model is None or gen_config is None:
        return model

    thinking_cfg = getattr(gen_config, "thinking_config", None)
    if thinking_cfg is None and isinstance(gen_config, dict):
        thinking_cfg = gen_config.get("thinking_config")
    if thinking_cfg is None:
        return model

    if not hasattr(model, "_additional_args") or not isinstance(model._additional_args, dict):
        return model

    if isinstance(thinking_cfg, dict):
        include_thoughts = thinking_cfg.get("include_thoughts")
        raw_level = thinking_cfg.get("thinking_level")
    else:
        include_thoughts = getattr(thinking_cfg, "include_thoughts", None)
        raw_level = getattr(thinking_cfg, "thinking_level", None)

    level_str: str | None = None
    if raw_level is not None:
        level_str = str(getattr(raw_level, "value", raw_level)).lower()

    if include_thoughts is False or level_str == "none":
        enable_thinking = False
    elif include_thoughts is True or level_str in {"minimal", "low", "medium", "high"}:
        enable_thinking = True
    else:
        return model

    import copy

    cloned = copy.copy(model)
    additional_args = copy.deepcopy(model._additional_args)

    extra_body = dict(additional_args.get("extra_body") or {})
    chat_template_kwargs = dict(extra_body.get("chat_template_kwargs") or {})
    chat_template_kwargs["enable_thinking"] = enable_thinking
    extra_body["chat_template_kwargs"] = chat_template_kwargs
    additional_args["extra_body"] = extra_body

    if enable_thinking and level_str in {"low", "medium", "high"}:
        additional_args["reasoning_effort"] = level_str
    elif not enable_thinking:
        additional_args.pop("reasoning_effort", None)

    cloned._additional_args = additional_args
    return cloned


__all__ = [
    "_get_genai_types",
    "apply_thinking_config_to_model",
    "resolve_generation_config",
]
