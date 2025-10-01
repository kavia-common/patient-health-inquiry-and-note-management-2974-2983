import os
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import requests

# PUBLIC_INTERFACE
@dataclass
class AIConfig:
    """Configuration for AI/NLP provider."""
    provider: str
    api_key: Optional[str]
    model: Optional[str]
    api_base: Optional[str]

    @staticmethod
    # PUBLIC_INTERFACE
    def from_env() -> "AIConfig":
        """Load configuration from environment variables.

        Required environment variables:
        - AI_PROVIDER: "openai" | "azure_openai" | "litellm" | "mock"
        - AI_API_KEY: The API key/token for the provider (not required for 'mock')
        - AI_MODEL: Model name (e.g., "gpt-4o-mini", "gpt-4o", "gpt-4o-mini-2024-07-18")
        - AI_API_BASE: Optional API base URL override (e.g., Azure OpenAI endpoint)
        """
        provider = os.getenv("AI_PROVIDER", "mock").strip().lower()
        api_key = os.getenv("AI_API_KEY")
        model = os.getenv("AI_MODEL", "gpt-4o-mini")
        api_base = os.getenv("AI_API_BASE")
        return AIConfig(provider=provider, api_key=api_key, model=model, api_base=api_base)

    # PUBLIC_INTERFACE
    def validate(self) -> Tuple[bool, Dict[str, Any]]:
        """Validate configuration and return (ok, details) with actionable hints."""
        details: Dict[str, Any] = {
            "provider": self.provider,
            "has_api_key": bool(self.api_key),
            "model": self.model,
            "api_base": self.api_base,
        }
        if self.provider == "mock":
            return True, {**details, "note": "Mock mode: no external API calls."}

        # For real providers, ensure api key and model
        if not self.api_key:
            return False, {**details, "hint": "Set AI_API_KEY in environment for provider."}
        if not self.model:
            return False, {**details, "hint": "Set AI_MODEL in environment for provider."}

        if self.provider == "azure_openai":
            if not self.api_base:
                return False, {**details, "hint": "Azure OpenAI requires AI_API_BASE (endpoint URL)."}
        # Others are fine with default bases.
        return True, details


# PUBLIC_INTERFACE
class AIClientError(Exception):
    """Raised for AI client errors."""


# PUBLIC_INTERFACE
class AIClient:
    """Thin wrapper for calling a chat completion/summarization provider.

    This client supports:
    - openai: Uses OpenAI Chat Completions API (via REST call).
    - azure_openai: Compatible REST call with API base and headers.
    - litellm: Use a proxy compatible with OpenAI format.
    - mock: Deterministic, offline mock for local testing.
    """

    def __init__(self, cfg: Optional[AIConfig] = None) -> None:
        self.cfg = cfg or AIConfig.from_env()

    def _headers(self) -> dict:
        if self.cfg.provider == "openai":
            if not self.cfg.api_key:
                raise AIClientError("AI_API_KEY is required for OpenAI provider.")
            return {
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            }
        if self.cfg.provider == "azure_openai":
            if not self.cfg.api_key:
                raise AIClientError("AI_API_KEY is required for Azure OpenAI provider.")
            return {
                "api-key": self.cfg.api_key,
                "Content-Type": "application/json",
            }
        if self.cfg.provider == "litellm":
            if not self.cfg.api_key:
                raise AIClientError("AI_API_KEY is required for LiteLLM provider.")
            return {
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            }
        return {"Content-Type": "application/json"}

    def _endpoint(self) -> str:
        # Endpoints are OpenAI-format compatible
        if self.cfg.provider == "openai":
            base = self.cfg.api_base or "https://api.openai.com/v1"
            return f"{base}/chat/completions"
        if self.cfg.provider == "azure_openai":
            base = self.cfg.api_base
            if not base:
                raise AIClientError("AI_API_BASE (Azure endpoint) is required for azure_openai.")
            # Azure format: {endpoint}/openai/deployments/{deployment-id}/chat/completions?api-version={version}
            # Assume AI_MODEL carries deployment-id or route. If model is missing, raise error.
            if not self.cfg.model:
                raise AIClientError("AI_MODEL (deployment name) is required for azure_openai.")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
            return f"{base}/openai/deployments/{self.cfg.model}/chat/completions?api-version={api_version}"
        if self.cfg.provider == "litellm":
            base = self.cfg.api_base or "http://localhost:4000"
            return f"{base}/v1/chat/completions"
        # mock doesn't call network
        return ""

    def _post(self, payload: dict) -> dict:
        # No network for mock
        if self.cfg.provider == "mock":
            # Respond with a naive echo/heuristic result
            messages = payload.get("messages", [])
            last_user = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = m.get("content", "")
                    break
            # Generate a basic follow-up based on keywords
            follow = "Could you tell me more about your symptoms, their duration, severity, and any medications you are taking?"
            low = (last_user or "").lower()
            if any(k in low for k in ["pain", "ache", "hurt"]):
                follow = "On a scale from 1-10, how severe is your pain, and when did it start?"
            elif any(k in low for k in ["fever", "temperature"]):
                follow = "What is your current temperature and how long have you had a fever?"
            elif "cough" in low:
                follow = "Is your cough dry or productive, and are there any triggers or times it worsens?"
            return {"choices": [{"message": {"content": follow}}]}

        url = self._endpoint()
        headers = self._headers()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
        except requests.exceptions.Timeout as e:
            raise AIClientError("AI provider request timed out. Check network/connectivity and try again.") from e
        except requests.exceptions.ConnectionError as e:
            raise AIClientError("Unable to reach AI provider endpoint. Verify AI_API_BASE/Internet connectivity.") from e
        except requests.exceptions.RequestException as e:
            raise AIClientError(f"Unexpected error contacting AI provider: {e}") from e

        if resp.status_code == 401:
            raise AIClientError("Unauthorized by AI provider (401). Verify AI_API_KEY is valid and not expired.")
        if resp.status_code == 404:
            raise AIClientError("AI endpoint or deployment not found (404). Check AI_API_BASE and AI_MODEL/deployment.")
        if resp.status_code >= 400:
            raise AIClientError(f"AI provider error {resp.status_code}: {resp.text}")
        return resp.json()

    # PUBLIC_INTERFACE
    def ask_follow_up(self, dialogue: List[dict]) -> str:
        """Return a single follow-up question based on conversation context.

        dialogue: list of {"role": "user"|"assistant", "content": "..."}
        """
        ok, detail = self.cfg.validate()
        if not ok:
            # Provide actionable hint but allow mock fallback if configured as such
            raise AIClientError(f"AI configuration invalid: {detail.get('hint') or 'Check environment variables.'}")

        system_prompt = (
            "You are a clinical intake assistant. Ask one concise, empathetic, "
            "health-related follow-up question based strictly on the patient's last message and prior context. "
            "Focus on clarifying symptoms, onset/duration, severity, medications, allergies, or red flags. "
            "Keep it under 30 words and ask only one question."
        )
        payload = {
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": system_prompt}] + dialogue,
            "temperature": 0.4,
            "n": 1,
            "max_tokens": 120,
        }
        data = self._post(payload)
        # OpenAI compatible response
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return (content or "").strip()

    # PUBLIC_INTERFACE
    def summarize_dialogue(self, dialogue: List[dict], patient_id: str) -> str:
        """Generate a concise clinical note from a conversation."""
        ok, detail = self.cfg.validate()
        if not ok:
            raise AIClientError(f"AI configuration invalid: {detail.get('hint') or 'Check environment variables.'}")

        system_prompt = (
            "You are a medical scribe. Create a clear, structured clinical intake note from the following conversation. "
            "Sections: Chief Concern, History of Present Illness (symptoms, onset/duration, severity, modifiers), "
            "Medications, Allergies, Relevant History, Red Flags, Plan/Next Steps. Keep it concise and factual. "
            "If information isn't provided, mark as 'Not specified'."
        )
        user_prompt = f"Patient ID: {patient_id}\nConversation:\n" + "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in dialogue
        )
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "n": 1,
            "max_tokens": 800,
        }
        data = self._post(payload)
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return (content or "").strip()

    # PUBLIC_INTERFACE
    def live_check(self) -> Dict[str, Any]:
        """Attempt a lightweight provider call to validate connectivity and credentials.

        Returns a dict describing success/failure and diagnostic hints.
        """
        # For mock, no real call needed
        if self.cfg.provider == "mock":
            ok, cfg = self.cfg.validate()
            return {"ok": ok, "provider": self.cfg.provider, "mode": "mock", "details": cfg}

        ok, details = self.cfg.validate()
        if not ok:
            return {"ok": False, "provider": self.cfg.provider, "details": details}

        try:
            payload = {
                "model": self.cfg.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Reply with a single word: ok."},
                ],
                "temperature": 0.0,
                "n": 1,
                "max_tokens": 2,
            }
            data = self._post(payload)
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return {"ok": True, "provider": self.cfg.provider, "content_preview": (content or "")[:50]}
        except AIClientError as e:
            return {
                "ok": False,
                "provider": self.cfg.provider,
                "error": str(e),
                "hint": "Verify AI_API_KEY, AI_MODEL, and AI_API_BASE (if Azure).",
            }
