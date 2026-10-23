"""
Google Gemini API client (the only generative AI the project uses).

One `generateContent` call over HTTPS with the standard library, so no SDK is needed. The key is sent in
the `x-goog-api-key` header, never in the URL, so it cannot end up in proxy or server logs.

    GEMINI_API_KEY   required to enable AI drafting (without it the writing tools still work by hand)
    GEMINI_MODEL     default "gemini-3.8-flash"
    GEMINI_TIMEOUT   seconds, default 60

Tests replace the client with `set_client(fake)`; a fake only needs `generate(system=, prompt=, json_output=)`
returning a `Result`.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException

logger = logging.getLogger("aec.writing")

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_OUTPUT_TOKENS = 8192  # room for the model's own reasoning tokens as well as a 1,500-word statement


class AssistantUnavailable(APIException):
    """Gemini could not be used. The message is safe to show; the cause is only logged."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The writing assistant is not available right now. Please try again in a few minutes."
    default_code = "assistant_unavailable"


class AssistantRefused(APIException):
    """Gemini declined the request (safety filters). Asking again with different wording may work."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = ("The writing assistant could not produce text for this request. "
                      "Check the student's answers for unusual content and try again.")
    default_code = "assistant_refused"


@dataclass
class Result:
    text: str
    model: str = ""
    usage: dict = field(default_factory=dict)  # prompt / output / total token counts


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: int = 60):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def generate(self, *, system: str, prompt: str, json_output: bool = False, temperature: float = 0.7) -> Result:
        config = {"temperature": temperature, "maxOutputTokens": MAX_OUTPUT_TOKENS}
        if json_output:
            config["responseMimeType"] = "application/json"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        request = urllib.request.Request(
            ENDPOINT.format(model=self.model), data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as res:  # noqa: S310 - fixed https URL
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The body can explain a bad key or quota; log its status only, never the request (student data).
            logger.error("Gemini returned HTTP %s for model %s", exc.code, self.model)
            if exc.code == 429:
                raise AssistantUnavailable("The writing assistant is busy (usage limit reached). "
                                           "Please wait a minute and try again.") from None
            raise AssistantUnavailable() from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.error("Gemini request failed: %s", type(exc).__name__)
            raise AssistantUnavailable() from None
        return parse_response(data, self.model)


def parse_response(data: dict, model: str) -> Result:
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise AssistantRefused()
    candidates = data.get("candidates") or []
    if not candidates:
        raise AssistantUnavailable()
    first = candidates[0]
    parts = (first.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        if first.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"):
            raise AssistantRefused()
        raise AssistantUnavailable()
    meta = data.get("usageMetadata") or {}
    usage = {"prompt": meta.get("promptTokenCount", 0), "output": meta.get("candidatesTokenCount", 0),
             "total": meta.get("totalTokenCount", 0)}
    return Result(text=text, model=data.get("modelVersion") or model, usage=usage)


_client = None


def set_client(client) -> None:
    """Swap the client (tests); None returns to the configured one."""
    global _client
    _client = client


def is_configured() -> bool:
    return _client is not None or bool(getattr(settings, "GEMINI_API_KEY", ""))


def get_client():
    if _client is not None:
        return _client
    if not getattr(settings, "GEMINI_API_KEY", ""):
        raise AssistantUnavailable("AI drafting is not set up on this server. "
                                   "An administrator needs to add a Gemini API key.")
    return GeminiClient(settings.GEMINI_API_KEY, settings.GEMINI_MODEL, settings.GEMINI_TIMEOUT)
