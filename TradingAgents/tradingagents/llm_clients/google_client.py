import re
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_GEMINI_VERSION = re.compile(r"^gemini-(\d+)\.(\d+)")


def _accepts_minimal_thinking(model: str) -> bool:
    """Whether ``thinking_level="minimal"`` is accepted: numbered Flash models
    before 3.8. Pro, 3.8+ and version-less aliases (which move between
    generations) are treated as rejecting it."""
    model_lc = model.lower()
    match = _GEMINI_VERSION.match(model_lc)
    return bool(match) and "pro" not in model_lc and (
        (int(match.group(1)), int(match.group(2))) < (3, 8)
    )


import os
import time
import logging
from pydantic import SecretStr
from google import genai

logger = logging.getLogger(__name__)


class KeyManager:
    _keys = None
    _idx = 0

    @classmethod
    def get_keys(cls):
        if cls._keys is None:
            cls._keys = []
            keys_file = r"d:\MyAgent\keys_valid.txt"
            if os.path.exists(keys_file):
                with open(keys_file, "r", encoding="utf-8") as f:
                    for line in f:
                        k = line.strip()
                        if k and not k.startswith("#"):
                            cls._keys.append(k)
        return cls._keys

    @classmethod
    def get_current_key(cls):
        keys = cls.get_keys()
        if not keys:
            return None
        return keys[cls._idx % len(keys)]

    @classmethod
    def next_key(cls):
        keys = cls.get_keys()
        if not keys:
            return None
        cls._idx = (cls._idx + 1) % len(keys)
        new_k = keys[cls._idx]
        os.environ["GOOGLE_API_KEY"] = new_k
        return new_k


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output and auto key-rotation on 429.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        keys = KeyManager.get_keys()
        max_attempts = max(len(keys), 4) if keys else 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                return normalize_content(super().invoke(input, config, **kwargs))
            except Exception as e:
                last_error = e
                err_str = str(e)
                is_quota = any(x in err_str.lower() for x in ["429", "resource_exhausted"])
                is_busy = any(x in err_str.lower() for x in ["503", "unavailable", "high demand", "overloaded"])

                if is_quota or is_busy:
                    new_key = KeyManager.next_key()
                    sleep_time = 3.0 if is_busy else 1.5
                    logger.warning(
                        "Google API %s: xoay sang key tiep theo va cho %ss...",
                        "server busy (503)" if is_busy else "quota (429)",
                        sleep_time,
                    )
                    if new_key:
                        self.google_api_key = SecretStr(new_key)
                        try:
                            self.client = genai.Client(api_key=new_key)
                        except Exception:
                            pass
                    time.sleep(sleep_time)
                    continue
                raise last_error
        if last_error:
            raise last_error


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "temperature", "max_output_tokens",
                    "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Unified api_key maps to provider-specific google_api_key
        google_api_key = self.kwargs.get("api_key") or self.kwargs.get("google_api_key")
        if not google_api_key:
            google_api_key = KeyManager.get_current_key()

        if google_api_key:
            llm_kwargs["google_api_key"] = google_api_key

        # Gemini 3.x takes the string ``thinking_level`` (the integer
        # ``thinking_budget`` was for the now-retired 2.5 line). Pro, Gemini
        # 3.8+ and the -latest aliases reject "minimal" with a 400; "low" is
        # accepted everywhere, so it is the fallback.
        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level:
            if thinking_level == "minimal" and not _accepts_minimal_thinking(self.model):
                thinking_level = "low"
            llm_kwargs["thinking_level"] = thinking_level

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
