"""OpenAI Responses API client for Microsoft Foundry."""

import asyncio
import logging
import os
import time
from urllib.parse import urlsplit

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from openai.types.responses import Response
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming

from mission_control.domain.errors import FoundryConfigError, ModelCallError
from mission_control.application.model_client import ModelText
from mission_control.log import elapsed_ms, one_line

logger = logging.getLogger(__name__)


def normalize_base_url(url: str) -> str:
    """Return a base URL the OpenAI client can append ``responses`` to."""
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
            "FOUNDRY_BASE_URL should be the resource host, or the full base ending in /."
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
    """One Responses API client for every pipeline step."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        json_mode: bool,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise FoundryConfigError("Set FOUNDRY_API_KEY to the key from your Foundry resource.")
        if not model.strip():
            raise FoundryConfigError("Set FOUNDRY_MODEL to the deployment name.")
        self._model = model.strip()
        self._json_mode = json_mode
        normalized = normalize_base_url(base_url)
        self._client = OpenAI(
            api_key=api_key,
            base_url=normalized,
            timeout=60.0,
            max_retries=0,
            http_client=http_client,
        )
        host = urlsplit(normalized).hostname
        assert host is not None
        logger.info(
            "Foundry client ready for deployment %s at %s, json mode %s.",
            self._model,
            host,
            "on" if self._json_mode else "off",
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
            json_mode=_json_mode_from_env(),
        )

    async def complete(self, *, step: str, system: str, user: str) -> ModelText:
        safe_step = one_line(step, limit=40)
        logger.debug(
            "Foundry step %s is sending %d system characters and %d user characters.",
            safe_step,
            len(system),
            len(user),
        )
        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(self._complete_sync, system, user)
        except ModelCallError as exc:
            _log_model_failure(safe_step, started, exc)
            raise
        logger.info(
            "Foundry step %s completed in %d ms, %d tokens in, %d tokens out.",
            safe_step,
            elapsed_ms(started),
            result.tokens_in,
            result.tokens_out,
        )
        return result

    def _complete_sync(self, system: str, user: str) -> ModelText:
        try:
            response = self._create(system, user)
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
        if response.status != "completed":
            raise ModelCallError("Foundry did not complete the response.")
        content = response.output_text
        if not isinstance(content, str) or not content.strip():
            raise ModelCallError("Foundry returned an empty reply.")
        usage = response.usage
        if usage is None:
            raise ModelCallError(
                "Foundry did not return token counts, so the cost cannot be calculated."
            )
        tokens_in = usage.input_tokens
        tokens_out = usage.output_tokens
        if not isinstance(tokens_in, int) or not isinstance(tokens_out, int):
            raise ModelCallError(
                "Foundry did not return token counts, so the cost cannot be calculated."
            )
        if tokens_in < 0 or tokens_out < 0:
            raise ModelCallError("Foundry returned a negative token count.")
        return ModelText(text=content, tokens_in=tokens_in, tokens_out=tokens_out)

    def _create(self, system: str, user: str) -> Response:
        params: ResponseCreateParamsNonStreaming = {
            "model": self._model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self._json_mode:
            params["text"] = {"format": {"type": "json_object"}}
        return self._client.responses.create(**params)


def _log_model_failure(step: str, started: float, exc: ModelCallError) -> None:
    elapsed = elapsed_ms(started)
    cause = exc.__cause__
    if isinstance(cause, APIStatusError):
        logger.error(
            "Foundry step %s failed after %d ms with HTTP %s: %s",
            step,
            elapsed,
            cause.status_code,
            exc.message,
        )
        return
    if isinstance(cause, APITimeoutError):
        logger.error("Foundry step %s timed out after %d ms: %s", step, elapsed, exc.message)
        return
    if isinstance(cause, APIConnectionError):
        logger.error(
            "Foundry step %s could not connect after %d ms: %s",
            step,
            elapsed,
            exc.message,
        )
        return
    logger.error("Foundry step %s failed after %d ms: %s", step, elapsed, exc.message)


def _json_mode_from_env() -> bool:
    raw = os.environ.get("FOUNDRY_JSON_MODE", "on").strip().lower()
    if raw in ("on", "true", "1"):
        return True
    if raw in ("off", "false", "0"):
        return False
    raise FoundryConfigError("FOUNDRY_JSON_MODE must be on or off.")
