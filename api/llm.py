"""
Provider factory — the ONE place a chat model is chosen. Configure via
CHAT_MODEL in .env ("provider:model", e.g. groq:llama-3.3-70b-versatile
or ollama:qwen3.5:9b). api/setup.py and evals/run.py both build here,
so the app and the evals can never drift onto different providers.
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

DEFAULT_CHAT_MODEL = f"google_genai:{os.environ.get('GEMINI_MODEL', 'gemini-3.1-flash-lite-preview')}"


def build_chat_model(temperature: float = 0.2):
    spec = os.environ.get("CHAT_MODEL", DEFAULT_CHAT_MODEL)
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
