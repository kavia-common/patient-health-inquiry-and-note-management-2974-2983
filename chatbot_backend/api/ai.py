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
            # Deterministic but varied heuristic based on last user message and some prior context.
            messages = payload.get("messages", [])
            # Collate dialogue user texts for context analysis
            user_texts = [m.get("content", "") for m in messages if m.get("role") == "user" and m.get("content")]
            last_user = user_texts[-1] if user_texts else ""
            lower = (last_user or "").lower()

            # Look back at earlier user content for additional hints
            earlier = " ".join(user_texts[:-1]).lower() if len(user_texts) > 1 else ""

            def choose(*options: str) -> str:
                # Pick an option based on simple hashing of the last_user to avoid the exact same string each time.
                if not options:
                    return ""
                idx = (sum(ord(c) for c in last_user) if last_user else 0) % len(options)
                return options[idx]

            # Symptom categories
            if any(k in lower for k in ["chest pain", "pressure in chest", "shortness of breath", "sob"]):
                follow = choose(
                    "Is the chest pain constant or intermittent, and does it worsen with activity?",
                    "Do you feel short of breath at rest or only with exertion, and when did this begin?",
                )
            elif any(k in lower for k in ["pain", "ache", "hurt", "sore"]):
                follow = choose(
                    "On a 1–10 scale, how severe is your pain and when did it start?",
                    "Where exactly is the pain located, and does anything make it better or worse?",
                    "Has the pain changed over time, and is it constant or does it come and go?",
                )
            elif any(k in lower for k in ["fever", "temperature", "chills", "sweats"]):
                follow = choose(
                    "What is your highest recent temperature and how long have you had a fever?",
                    "Are you experiencing chills or night sweats, and when did this begin?",
                )
            elif "cough" in lower or "phlegm" in lower or "sputum" in lower:
                follow = choose(
                    "Is your cough dry or producing phlegm, and when did it start?",
                    "Do you notice any triggers or times of day when the cough worsens?",
                )
            elif any(k in lower for k in ["headache", "migraine"]):
                follow = choose(
                    "Where is the headache located, and how severe is it on a 1–10 scale?",
                    "Did the headache start suddenly or gradually, and any sensitivity to light or nausea?",
                )
            elif any(k in lower for k in ["nausea", "vomit", "diarrhea", "stomach", "abdomen", "abdominal"]):
                follow = choose(
                    "Have you had vomiting or diarrhea, and when did these symptoms begin?",
                    "Where in your abdomen is the discomfort, and is it related to meals?",
                )
            elif any(k in lower for k in ["rash", "itch", "hives", "skin"]):
                follow = choose(
                    "Where did the rash start and has it spread, and are you experiencing itching?",
                    "Any new products, medications, or exposures before the rash appeared?",
                )
            elif any(k in lower for k in ["dizzy", "lightheaded", "faint"]):
                follow = choose(
                    "When do you feel dizzy, and does it occur with standing or turning your head?",
                    "Any recent falls, vision changes, or new medications?",
                )
            else:
                # Generic but concise and varied question grounded in triage needs
                if any(k in earlier for k in ["allerg", "penicillin", "sulfa", "peanut"]):
                    follow = "Do you have any medication or food allergies we should note?"
                elif any(k in earlier for k in ["ibuprofen", "acetaminophen", "paracetamol", "antibiotic", "inhaler", "insulin"]):
                    follow = "What medications or supplements are you currently taking and their doses?"
                else:
                    follow = choose(
                        "How long have these symptoms been present, and are they getting better or worse?",
                        "Have you taken any medications or remedies, and did they help?",
                        "Do you have any allergies to medications or foods?",
                    )

            # Ensure a trailing question mark and concise length
            follow = follow.strip()
            if not follow.endswith("?"):
                follow += "?"
            if len(follow) > 180:
                follow = follow[:177].rstrip() + "?"

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

        # Build a short synopsis to foreground the last user message while preserving full context.
        last_user = ""
        prior_user_context = []
        for m in reversed(dialogue):
            if m.get("role") == "user" and m.get("content"):
                if not last_user:
                    last_user = m["content"]
                else:
                    # collect up to a few prior user messages for added context variety
                    if len(prior_user_context) < 3:
                        prior_user_context.append(m["content"])
            if last_user and len(prior_user_context) >= 3:
                break
        prior_user_context = list(reversed(prior_user_context))

        system_prompt = (
            "You are an empathetic medical triage assistant for clinical intake. Your task is to ask exactly ONE "
            "concise follow‑up question based on the patient's latest message, taking prior context into account. "
            "Prioritize clarifying symptoms, onset/duration, severity (1–10), progression, relevant meds, allergies, "
            "red flags (e.g., chest pain, shortness of breath, confusion), or needed specifics for safe triage. "
            "Do not provide advice or multiple questions. Keep the question under 30 words and end with a question mark."
        )

        # We prepend a brief context primer so models focus on the most recent message.
        primer = "Context summary for the assistant:\n"
        if prior_user_context:
            primer += "Earlier patient details:\n- " + "\n- ".join(s.strip() for s in prior_user_context if s.strip()) + "\n"
        if last_user:
            primer += f"Most recent patient message: {last_user.strip()}\n"

        messages = [{"role": "system", "content": system_prompt}]
        # Provide a user turn that summarizes context to bias the model toward the latest info,
        # then include the full dialogue so the provider can ground the response.
        if primer.strip():
            messages.append({"role": "user", "content": primer})
        messages.extend(dialogue)

        payload = {
            "model": self.cfg.model,
            "messages": messages,
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
            "Sections: Chief Concern; History of Present Illness (symptoms, onset/duration, severity, course, modifiers); "
            "Medications; Allergies; Relevant History; Red Flags; Plan/Next Steps. Keep it concise and factual. "
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
