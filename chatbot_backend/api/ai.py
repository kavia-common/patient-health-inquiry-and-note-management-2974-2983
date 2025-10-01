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
            # Deterministic, domain-aware mock that identifies complaint and asks issue-specific follow-ups.
            messages = payload.get("messages", [])
            # Extract a possible explicit "conclusion" request from system/user content
            sys_user_text = " ".join(
                m.get("content", "") for m in messages if m.get("role") in ("system", "user")
            ).lower()
            wants_conclusion = ("concluding summary" in sys_user_text) or ("compose a concluding summary" in sys_user_text)

            user_texts = [m.get("content", "") for m in messages if m.get("role") == "user" and m.get("content")]
            last_user = user_texts[-1] if user_texts else ""
            lower = (last_user or "").lower()
            earlier = " ".join(user_texts[:-1]).lower() if len(user_texts) > 1 else ""

            def choose(*options: str) -> str:
                if not options:
                    return ""
                idx = (sum(ord(c) for c in last_user) if last_user else 0) % len(options)
                return options[idx]

            # Detect key complaint tokens to name the issue
            issue_tokens = [
                ("chest pain", ["chest pain", "pressure in chest"]),
                ("shortness of breath", ["shortness of breath", "sob"]),
                ("headache", ["headache", "migraine"]),
                ("cough", ["cough", "phlegm", "sputum"]),
                ("fever", ["fever", "temperature", "chills", "sweats"]),
                ("abdominal pain", ["stomach", "abdomen", "abdominal", "belly pain"]),
                ("nausea/vomiting/diarrhea", ["nausea", "vomit", "diarrhea"]),
                ("rash", ["rash", "itch", "hives", "skin", "lesion"]),
                ("dizziness", ["dizzy", "lightheaded", "faint"]),
                ("generalized pain", ["pain", "ache", "hurt", "sore", "tender", "cramp"]),
                ("fatigue", ["fatigue", "tired", "weakness"]),
                ("swelling", ["swelling", "edema"]),
            ]

            def detect_issue(text: str) -> str | None:
                txt = text.lower()
                for label, kws in issue_tokens:
                    if any(k in txt for k in kws):
                        return label
                return None

            combined_user = (earlier + " " + lower).strip()
            issue_label = detect_issue(combined_user)

            # If conclusion requested, synthesize an explicit issue-specific summary
            if wants_conclusion:
                duration_hint = ""
                for kw in ["since", "for ", "days", "weeks", "months", "yesterday", "today", "this morning", "this evening"]:
                    if kw in combined_user:
                        duration_hint = " with reported duration details"
                        break
                severity_hint = ""
                for kw in ["1/10", "2/10", "3/10", "4/10", "5/10", "6/10", "7/10", "8/10", "9/10", "10/10", "mild", "moderate", "severe"]:
                    if kw in combined_user:
                        severity_hint = " and severity discussed"
                        break
                meds_hint = "; medications mentioned" if any(k in combined_user for k in ["ibuprofen","acetaminophen","paracetamol","antibiotic","inhaler","insulin","mg","dose","tablet","pill"]) else ""
                allerg_hint = "; no allergies noted" if ("allerg" not in combined_user) else "; allergies discussed"
                main_issue = issue_label or "chief complaint not clearly specified"
                # Craft concise, named-issue summary
                return {
                    "choices": [{
                        "message": {
                            "content": f"Conclusion: Patient presents with {main_issue}{duration_hint}{severity_hint}. Course and modifiers addressed as provided{meds_hint}{allerg_hint}."
                        }
                    }]
                }

            # Determine if the user has described any chief complaint yet
            has_complaint = issue_label is not None

            if not has_complaint:
                follow = choose(
                    "What is the main health concern or symptom you’re experiencing today?",
                    "Could you describe your primary symptom or health issue right now?",
                    "What brought you in today—what symptom or problem is bothering you most?"
                )
            elif issue_label in ["chest pain", "shortness of breath"]:
                follow = choose(
                    "Is the chest pain constant or intermittent, and does exertion make it worse?",
                    "Do you feel short of breath at rest or only with activity, and when did it begin?",
                )
            elif issue_label == "generalized pain":
                follow = choose(
                    "On a 1–10 scale, how severe is your pain and when did it start?",
                    "Where exactly is the pain located, and does anything make it better or worse?",
                    "Is the pain constant or does it come and go, and has it changed?"
                )
            elif issue_label == "fever":
                follow = choose(
                    "What is your highest recent temperature and how long have you had a fever?",
                    "Are you experiencing chills or night sweats, and when did this begin?"
                )
            elif issue_label == "cough":
                follow = choose(
                    "Is your cough dry or producing phlegm, and when did it start?",
                    "Do you notice any triggers or times of day when the cough worsens?"
                )
            elif issue_label == "headache":
                follow = choose(
                    "Where is the headache located, and how severe is it on a 1–10 scale?",
                    "Did the headache start suddenly or gradually, and any light sensitivity or nausea?"
                )
            elif issue_label in ["abdominal pain", "nausea/vomiting/diarrhea"]:
                follow = choose(
                    "Have you had vomiting or diarrhea, and when did these symptoms begin?",
                    "Where in your abdomen is the discomfort, and is it related to meals?"
                )
            elif issue_label == "rash":
                follow = choose(
                    "Where did the rash start and has it spread, and are you experiencing itching?",
                    "Any new products, medications, or exposures before the rash appeared?"
                )
            elif issue_label == "dizziness":
                follow = choose(
                    "When do you feel dizzy, and does it occur with standing or turning your head?",
                    "Any recent falls, vision changes, or new medications?"
                )
            else:
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
        """Return a single follow-up question or a concluding summary based on conversation context.

        dialogue: list of {"role": "user"|"assistant", "content": "..."}
        Special behavior:
        - If the last system message asks for a conclusion or the last user message contains 'Compose a concluding summary',
          the model should produce a concise 'Conclusion:' paragraph and not ask a question.
        """
        ok, detail = self.cfg.validate()
        if not ok:
            raise AIClientError(f"AI configuration invalid: {detail.get('hint') or 'Check environment variables.'}")

        # Detect if we are in conclusion mode by scanning the last few instruction turns
        conclusion_mode = False
        for m in reversed(dialogue[-6:]):
            role = m.get("role")
            content = (m.get("content") or "").lower()
            if role in ("system", "user") and ("concluding summary" in content or content.startswith("conclusion:")):
                conclusion_mode = True
                break

        # Build a short synopsis to foreground the last user message while preserving full context.
        last_user = ""
        prior_user_context = []
        for m in reversed(dialogue):
            if m.get("role") == "user" and m.get("content"):
                if not last_user:
                    last_user = m["content"]
                else:
                    if len(prior_user_context) < 4:
                        prior_user_context.append(m["content"])
            if last_user and len(prior_user_context) >= 4:
                break
        prior_user_context = list(reversed(prior_user_context))

        # System prompt with embedded examples to steer good vs bad behavior
        if conclusion_mode:
            system_prompt = (
                "You are a medical intake assistant. The intake is nearly complete. "
                "Write a brief concluding summary grounded in the patient's chief complaint (name it explicitly), and include key details "
                "(onset/duration, severity, progression/modifiers), notable medications/allergies/relevant history, and any red flags. "
                "Keep it concise (2–4 sentences), neutral, and factual. Start with 'Conclusion:' and do not ask questions.\n"
                "Bad example: 'Any other concerns? Also what meds do you take?' (multiple questions)\n"
                "Good examples:\n"
                "- 'Conclusion: Patient presents with headache localized to the forehead for ~4 hours, severity 6/10; no meds taken; no known allergies. No neuro red flags reported.'\n"
                "- 'Conclusion: 3 days of productive cough with mild fever; symptoms gradually worsening; using acetaminophen; denies chest pain or dyspnea; no red flags disclosed.'"
            )
        else:
            system_prompt = (
                "You are an empathetic medical triage assistant for clinical intake. Use full recent context, "
                "do not repeat previously covered domains, and ask exactly ONE concise follow‑up.\n"
                "Rules:\n"
                "- If no chief complaint appears, ask only for the main symptom/concern.\n"
                "- Once a complaint exists, progress through missing domains: onset/duration, severity (1–10), "
                "progression, modifiers, medications, allergies, relevant history, red flags.\n"
                "- Keep under 28 words, end with a question mark, and avoid multiple questions.\n"
                "Bad example: 'When did it start and how severe? Any triggers?'.\n"
                "Good examples:\n"
                "- 'When did the symptoms begin, and have they changed since?'\n"
                "- 'What makes the pain better or worse?'"
            )

        # We prepend a brief context primer so models focus on the most recent message.
        primer = "Context summary for the assistant:\n"
        if prior_user_context:
            primer += "Earlier patient details:\n- " + "\n- ".join(s.strip() for s in prior_user_context if s.strip()) + "\n"
        if last_user:
            primer += f"Most recent patient message: {last_user.strip()}\n"

        messages = [{"role": "system", "content": system_prompt}]
        if primer.strip():
            messages.append({"role": "user", "content": primer})
        messages.extend(dialogue)

        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": 0.25 if conclusion_mode else 0.35,
            "n": 1,
            "max_tokens": 220 if conclusion_mode else 120,
        }

        # Mock provider branch: generate deterministic content without network.
        # Add small rule-based diversification to avoid static templates across turns.
        if self.cfg.provider == "mock":
            # Use last few user turns to diversify content and avoid repetition.
            user_texts = [m.get("content", "") for m in messages if m.get("role") == "user" and m.get("content")]
            last_user_text = user_texts[-1] if user_texts else ""
            recent_context = " ".join(user_texts[-3:]).lower()
            lower = (last_user_text or "").lower()

            def choose(seed: str, *options: str) -> str:
                if not options:
                    return ""
                # Use a simple hash on the seed to pick a variant deterministically
                idx = (sum(ord(c) for c in seed) if seed else 0) % len(options)
                return options[idx]

            # Build a small domain memory by inspecting recent context
            complaint_markers = [
                "pain", "ache", "hurt", "sore", "fever", "temperature", "chills", "sweats",
                "cough", "phlegm", "sputum", "headache", "migraine", "nausea", "vomit",
                "diarrhea", "stomach", "abdomen", "abdominal", "rash", "itch", "hives",
                "skin", "dizzy", "lightheaded", "faint", "shortness of breath", "sob",
                "chest pain"
            ]
            has_complaint = any(k in recent_context for k in complaint_markers)

            if conclusion_mode:
                flags = []
                if any(k in recent_context for k in ["worse", "better", "improve", "gradual", "sudden"]):
                    flags.append("progression noted")
                if any(k in recent_context for k in ["mild", "moderate", "severe", "/10"]):
                    flags.append("severity addressed")
                if any(k in recent_context for k in ["since", "for ", "days", "weeks", "months", "yesterday", "today"]):
                    flags.append("onset/duration captured")
                if any(k in recent_context for k in ["allerg", "penicillin", "sulfa", "peanut"]):
                    flags.append("allergies documented")
                if any(k in recent_context for k in ["ibuprofen", "acetaminophen", "paracetamol", "antibiotic", "inhaler", "insulin", "mg"]):
                    flags.append("medications mentioned")
                summary_hint = ", ".join(flags) if flags else "core intake details summarized"
                return f"Conclusion: Intake summary with {summary_hint}. No further clarifying questions at this time."

            if not has_complaint:
                follow = choose(
                    last_user_text,
                    "What is the main health concern or symptom you’re experiencing today?",
                    "Could you briefly describe your primary symptom right now?",
                    "What brought you in today—what symptom is bothering you most?"
                )
            elif any(k in lower for k in ["chest pain", "pressure in chest", "shortness of breath", "sob"]):
                follow = choose(
                    last_user_text,
                    "Is the chest pain constant or intermittent, and does exertion make it worse?",
                    "Do you feel short of breath at rest or only with activity, and when did it begin?"
                )
            elif any(k in lower for k in ["pain", "ache", "hurt", "sore"]):
                follow = choose(
                    last_user_text,
                    "On a 1–10 scale, how severe is your pain and when did it start?",
                    "Where is the pain located, and what makes it better or worse?",
                    "Is the pain constant or does it come and go, and has it changed?"
                )
            elif any(k in lower for k in ["fever", "temperature", "chills", "sweats"]):
                follow = choose(
                    last_user_text,
                    "What is your highest recent temperature and how long have you had a fever?",
                    "Are you experiencing chills or night sweats, and when did this begin?"
                )
            elif "cough" in lower or "phlegm" in lower or "sputum" in lower:
                follow = choose(
                    last_user_text,
                    "Is your cough dry or producing phlegm, and when did it start?",
                    "Do you notice any triggers or times of day when the cough worsens?"
                )
            elif any(k in lower for k in ["headache", "migraine"]):
                follow = choose(
                    last_user_text,
                    "Where is the headache located, and how severe is it on a 1–10 scale?",
                    "Did the headache start suddenly or gradually, and any light sensitivity or nausea?"
                )
            elif any(k in lower for k in ["nausea", "vomit", "diarrhea", "stomach", "abdomen", "abdominal"]):
                follow = choose(
                    last_user_text,
                    "Have you had vomiting or diarrhea, and when did these symptoms begin?",
                    "Where in your abdomen is the discomfort, and is it related to meals?"
                )
            elif any(k in lower for k in ["rash", "itch", "hives", "skin"]):
                follow = choose(
                    last_user_text,
                    "Where did the rash start and has it spread, and are you experiencing itching?",
                    "Any new products, medications, or exposures before the rash appeared?"
                )
            elif any(k in lower for k in ["dizzy", "lightheaded", "faint"]):
                follow = choose(
                    last_user_text,
                    "When do you feel dizzy, and does it occur with standing or turning your head?",
                    "Any recent falls, vision changes, or new medications?"
                )
            else:
                # Pivot based on hints in prior content to diversify
                if any(k in recent_context for k in ["allerg", "penicillin", "sulfa", "peanut"]):
                    follow = "Do you have any medication or food allergies we should note?"
                elif any(k in recent_context for k in ["ibuprofen", "acetaminophen", "paracetamol", "antibiotic", "inhaler", "insulin", "supplement", "vitamin"]):
                    follow = choose(
                        last_user_text,
                        "What medications or supplements are you currently taking and their doses?",
                        "Are you taking any over-the-counter medicines or supplements?"
                    )
                elif any(k in recent_context for k in ["since", "for ", "days", "weeks", "months"]):
                    follow = choose(
                        last_user_text,
                        "Has the symptom been getting better, worse, or staying the same?",
                        "What makes the symptom better or worse?"
                    )
                else:
                    follow = choose(
                        last_user_text,
                        "How long have these symptoms been present, and are they changing?",
                        "Have you taken any medications or remedies, and did they help?",
                        "Do you have any allergies to medications or foods?"
                    )

            follow = follow.strip()
            if not follow.endswith("?"):
                follow += "?"
            # Shorten if too long, preserving question mark
            if len(follow) > 160:
                follow = follow[:157].rstrip(" ,.;") + "?"
            return follow

        # Real providers
        data = self._post(payload)
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        # Surface empty content upstream; downstream will handle showing empty/null in UI and logging errors.
        return (content or "").strip()

    # PUBLIC_INTERFACE
    def summarize_dialogue(self, dialogue: List[dict], patient_id: str) -> str:
        """Generate a concise clinical note from a conversation."""
        ok, detail = self.cfg.validate()
        if not ok:
            raise AIClientError(f"AI configuration invalid: {detail.get('hint') or 'Check environment variables.'}")

        system_prompt = (
            "You are a medical scribe. Create a clear, structured clinical intake note from the following conversation. "
            "Explicitly identify and name the main issue in 'Chief Concern' (e.g., 'headache', 'cough', 'abdominal pain'). "
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
