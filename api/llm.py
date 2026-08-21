"""
Provider factory — the ONE place a chat model is chosen, with per-task
routing between two roles:

  "fast"  — cheap/simple nodes (intake extraction, clarify question)
  "smart" — anywhere a wrong call is expensive (tool routing in
            retrieve, the final answer, the compliance verdict, the
            answer-scoring judge)

Configure per role via CHAT_MODEL_FAST / CHAT_MODEL_SMART in .env
("provider:model", e.g. groq:llama-3.1-8b-instant). CHAT_MODEL alone
still works as a single override for both roles (e.g. the evals
bake-off trick, or pinning everything to one local Ollama model).
api/setup.py and evals/run.py both build here, so the app and the
evals can never drift onto different providers.
"""

from __future__ import annotations

import importlib
import os

from langchain.chat_models import init_chat_model

# Providers init_chat_model's registry doesn't know — instantiated
# directly. The class reads its own API key env var.
_EXTRA_PROVIDERS = {
    "cerebras": ("langchain_cerebras", "ChatCerebras"),
}

# Both free on Groq (console.groq.com, no card required): a small,
# fast model for cheap/simple nodes and a larger one for anywhere a
# wrong call is expensive.
DEFAULT_MODELS = {
    "fast": "groq:llama-3.1-8b-instant",
    "smart": "groq:llama-3.3-70b-versatile",
}

ROLES = tuple(DEFAULT_MODELS)


def build_chat_model(role: str = "smart", temperature: float = 0.2):
    if role not in DEFAULT_MODELS:
        raise ValueError(f"unknown model role {role!r}, expected one of {ROLES}")

    spec = (
        os.environ.get(f"CHAT_MODEL_{role.upper()}")
        or os.environ.get("CHAT_MODEL")
        or DEFAULT_MODELS[role]
    )
    provider, _, model_name = spec.partition(":")

    extra_kwargs: dict = {}
    if provider == "ollama":
        # Ollama defaults num_ctx low (~4096) and silently truncates
        # longer prompts — raise it so retrieve/present prompts fit.
        extra_kwargs["num_ctx"] = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))

    if provider in _EXTRA_PROVIDERS:
        module_name, class_name = _EXTRA_PROVIDERS[provider]
        chat_class = getattr(importlib.import_module(module_name), class_name)
        return chat_class(model=model_name, temperature=temperature, **extra_kwargs)
    return init_chat_model(spec, temperature=temperature, **extra_kwargs)
