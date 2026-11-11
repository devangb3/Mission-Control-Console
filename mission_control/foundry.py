"""Azure AI Inference SDK for Microsoft Foundry chat completions.
"""

import asyncio
import os
from urllib.parse import urlsplit

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from mission_control.errors import FoundryConfigError, ModelCallError
from mission_control.model_client import ModelText


def normalize_base_url(url: str) -> str:
    """Return a base URL the OpenAI client can append ``chat/completions`` to."""
    cleaned = url.strip().rstrip("/")
    if cleaned == "":
        raise FoundryConfigError("Set FOUNDRY_BASE_URL to your Foundry resource URL.")
    if cleaned.endswith("/openai/v1"):
        _require_https(cleaned)
        return cleaned + "/"
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or not parsed.hostname:
        raise FoundryConfigError("FOUNDRY_BASE_URL must be an https URL.")
    if parsed.path not in ("", "/"):
        raise FoundryConfigError(
            "FOUNDRY_BASE_URL should be the resource host, or the full base ending in /openai/v1/."
        )
    host = parsed.hostname
    if host.endswith(".openai.azure.com") or host.endswith(".services.ai.azure.com"):
        return cleaned + "/openai/v1/"
    raise FoundryConfigError(
        "FOUNDRY_BASE_URL must be an openai.azure.com or services.ai.azure.com host, "
        "or a base URL ending in /openai/v1/."
    )


def _require_https(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise FoundryConfigError("FOUNDRY_BASE_URL must start with https://.")


class FoundryModelClient:
    """One chat-completions client for every pipeline step."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float | None,
        json_mode: bool,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise FoundryConfigError("Set FOUNDRY_API_KEY to the key from your Foundry resource.")
        if not model.strip():
            raise FoundryConfigError("Set FOUNDRY_MODEL to the deployment name.")
        self._model = model.strip()
        self._temperature = temperature
        self._json_mode = json_mode
        self._client = OpenAI(
            api_key=api_key,
            base_url=normalize_base_url(base_url),
            timeout=60.0,
            max_retries=0,
            http_client=http_client,
        )

    @classmethod
    def from_env(cls) -> "FoundryModelClient":
        api_key = os.environ.get("FOUNDRY_API_KEY", "").strip()
        base_url = os.environ.get("FOUNDRY_BASE_URL", "").strip()
        model = os.environ.get("FOUNDRY_MODEL", "").strip()
        if not api_key:
            raise FoundryConfigError("Set FOUNDRY_API_KEY to the key from your Foundry resource.")
        if not base_url:
            raise FoundryConfigError("Set FOUNDRY_BASE_URL to your Foundry resource URL.")
        if not model:
            raise FoundryConfigError("Set FOUNDRY_MODEL to the deployment name.")
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=_temperature_from_env(),
            json_mode=_json_mode_from_env(),
        )

    async def complete(self, *, step: str, system: str, user: str) -> ModelText:
        del step
        return await asyncio.to_thread(self._complete_sync, system, user)

    def _complete_sync(self, system: str, user: str) -> ModelText:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            response = self._create(messages)
        except APITimeoutError as exc:
            raise ModelCallError("Foundry did not answer in time. File the report again.") from exc
        except APIStatusError as exc:
            if exc.status_code in (401, 403):
                raise ModelCallError("Foundry refused the API key.") from exc
            raise ModelCallError(f"Foundry rejected the request ({exc.status_code}).") from exc
        except APIConnectionError as exc:
            raise ModelCallError(
                "Could not reach Foundry. Check the network and file the report again."
            ) from exc
        if not response.choices:
            raise ModelCallError("Foundry returned no choices.")
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ModelCallError("Foundry returned an empty reply.")
        usage = response.usage
        if usage is None:
            raise ModelCallError(
                "Foundry did not return token counts, so the cost cannot be calculated."
            )
        tokens_in = usage.prompt_tokens
        tokens_out = usage.completion_tokens
        if not isinstance(tokens_in, int) or not isinstance(tokens_out, int):
            raise ModelCallError(
                "Foundry did not return token counts, so the cost cannot be calculated."
            )
        if tokens_in < 0 or tokens_out < 0:
            raise ModelCallError("Foundry returned a negative token count.")
        return ModelText(text=content, tokens_in=tokens_in, tokens_out=tokens_out)

    def _create(self, messages: list[dict[str, str]]) -> object:
        json_format = {"type": "json_object"}
        if self._json_mode and self._temperature is not None:
            return self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                response_format=json_format,  # type: ignore[arg-type]
            )
        if self._json_mode:
            return self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                response_format=json_format,  # type: ignore[arg-type]
            )
        if self._temperature is not None:
            return self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
            )
        return self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
        )


def _temperature_from_env() -> float | None:
    raw = os.environ.get("FOUNDRY_TEMPERATURE", "0").strip()
    if raw.lower() == "omit":
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise FoundryConfigError("FOUNDRY_TEMPERATURE must be a number or omit.") from exc
    if not 0 <= value <= 2:
        raise FoundryConfigError("FOUNDRY_TEMPERATURE must be between 0 and 2, or omit.")
    return value


def _json_mode_from_env() -> bool:
    raw = os.environ.get("FOUNDRY_JSON_MODE", "on").strip().lower()
    if raw in ("on", "true", "1"):
        return True
    if raw in ("off", "false", "0"):
        return False
    raise FoundryConfigError("FOUNDRY_JSON_MODE must be on or off.")
