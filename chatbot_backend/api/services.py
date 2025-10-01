import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

from django.utils import timezone

from .models import Conversation, Message
from .ai import AIClient

# PUBLIC_INTERFACE
@dataclass
class ConversationManager:
    """Manage conversations and messages."""

    # PUBLIC_INTERFACE
    def start_conversation(self, patient_id: str, metadata: dict | None = None) -> Conversation:
        """Start a new conversation for a patient."""
        convo = Conversation.objects.create(patient_id=patient_id, metadata=metadata or {})
        return convo

    # PUBLIC_INTERFACE
    def append_messages(self, conversation_id: uuid.UUID, messages: List[Tuple[str, str]]) -> Conversation:
        """Append messages to an existing conversation.
        messages: list of (sender, text)
        """
        convo = Conversation.objects.get(id=conversation_id)
        for sender, text in messages:
            Message.objects.create(conversation=convo, sender=sender, text=text)
        convo.updated_at = timezone.now()
        convo.save(update_fields=["updated_at"])
        return convo

    # PUBLIC_INTERFACE
    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        """Retrieve a conversation."""
        return Conversation.objects.get(id=conversation_id)


# PUBLIC_INTERFACE
class NoteGenerator:
    """Generate a disease note using AI with a rule-based fallback."""

    def __init__(self, ai: AIClient | None = None) -> None:
        self.ai = ai or AIClient()

    # PUBLIC_INTERFACE
    def generate_note(self, conversation: Conversation, note_title: str = "") -> Tuple[str, str]:
        """Generate a note text from a conversation using AI if configured; fallback to heuristic.

        Returns (title, text).
        """
        messages = conversation.messages.all()
        dialogue = []
        for m in messages:
            role = "user" if m.sender == "patient" else "assistant"
            dialogue.append({"role": role, "content": m.text})

        title = note_title.strip() or f"Disease Note for Patient {conversation.patient_id}"

        try:
            ai_text = self.ai.summarize_dialogue(dialogue=dialogue, patient_id=conversation.patient_id)
            text = f"Title: {title}\nConversation ID: {conversation.id}\nPatient ID: {conversation.patient_id}\n\n{ai_text}"
            return title, text
        except Exception:
            # Fallback to prior heuristic composition
            patient_lines = [m.text.strip() for m in messages if m.sender == "patient" and m.text.strip()]
            bot_lines = [m.text.strip() for m in messages if m.sender == "bot" and m.text.strip()]

            symptoms = []
            duration = None
            severity = None
            meds = []
            allergies = []
            concerns = []

            for line in patient_lines:
                low = line.lower()
                if any(k in low for k in ["pain", "fever", "cough", "nausea", "headache", "dizzy", "rash", "fatigue", "sore"]):
                    symptoms.append(line)
                if "week" in low or "day" in low or "month" in low:
                    duration = line if duration is None else duration
                if any(k in low for k in ["mild", "moderate", "severe", "worse", "improving"]):
                    severity = line if severity is None else severity
                if any(k in low for k in ["med", "medicine", "drug", "pill", "ibuprofen", "acetaminophen", "paracetamol", "antibiotic"]):
                    meds.append(line)
                if "allerg" in low:
                    allergies.append(line)
                if any(k in low for k in ["concern", "worried", "afraid"]):
                    concerns.append(line)

            lines = [
                f"Title: {title}",
                f"Conversation ID: {conversation.id}",
                f"Patient ID: {conversation.patient_id}",
                f"Created: {conversation.created_at.isoformat()}",
                f"Updated: {conversation.updated_at.isoformat()}",
                "",
                "Chief Concerns:",
                *([f"- {c}" for c in concerns] or ["- Not specified"]),
                "",
                "Reported Symptoms:",
                *([f"- {s}" for s in symptoms] or ["- Not specified"]),
                "",
                "Duration:",
                f"- {duration or 'Not specified'}",
                "",
                "Severity:",
                f"- {severity or 'Not specified'}",
                "",
                "Medications:",
                *([f"- {m}" for m in meds] or ["- Not specified"]),
                "",
                "Allergies:",
                *([f"- {a}" for a in allergies] or ["- Not specified"]),
                "",
                "Context (last bot prompts):",
                *([f"- {b}" for b in bot_lines[-3:]] or ["- Not available"]),
                "",
                "Generated At:",
                f"- {datetime.utcnow().isoformat()}Z",
            ]
            return title, "\n".join(lines)


# PUBLIC_INTERFACE
class LocalNoteStorageError(Exception):
    """Raised when saving a note to local storage fails."""
    pass


# PUBLIC_INTERFACE
class LocalNoteStorage:
    """Save notes to a configurable local directory (e.g., synced OneDrive folder).

    Uses environment variables for flexibility:
    - ONEDRIVE_SAVE_DIR: Preferred path to save notes (e.g., OneDrive synced directory)
      Fallback is C:\\Nilesh_TATA\\Prescription for backward compatibility.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        """
        base_dir: target directory to save notes. If None, uses env ONEDRIVE_SAVE_DIR or legacy path.
        """
        default_legacy = r"C:\\Nilesh_TATA\\Prescription"
        self.base_dir = base_dir or os.getenv("ONEDRIVE_SAVE_DIR", default_legacy)

    # PUBLIC_INTERFACE
    def save_text_file(self, filename: str, content: str) -> dict:
        """
        Save the given content as a .txt file in the base directory.

        Returns a dict with details: { "path": ..., "bytes_written": ..., "filename": ... }
        Raises LocalNoteStorageError on failures.
        """
        try:
            # Ensure directory exists
            os.makedirs(self.base_dir, exist_ok=True)

            # Ensure .txt extension
            if not filename.lower().endswith(".txt"):
                filename = f"{filename}.txt"

            # Normalize filename to avoid path traversal
            safe_name = os.path.basename(filename)
            target_path = os.path.join(self.base_dir, safe_name)

            data = content.encode("utf-8")
            with open(target_path, "wb") as f:
                f.write(data)

            return {
                "path": target_path,
                "bytes_written": len(data),
                "filename": safe_name,
            }
        except Exception as e:
            raise LocalNoteStorageError(f"Failed to save file locally: {e}") from e


# PUBLIC_INTERFACE
class AIConversationHelper:
    """Helper that uses AI to generate dynamic follow-up questions based on stored conversation.

    The AI provider is configured via environment variables (see .env.example and AI_INTEGRATION.md).
    If AI is set to 'mock', a deterministic, symptom-aware follow-up is returned without external API calls.

    Enhancement:
    - Tracks which clinical intake domains have been asked (domains_asked)
    - Avoids repeating domains within a window
    - Advances through domains until enough data is gathered
    - When sufficient coverage is reached, emits a 'conclusion' summary for the bot to send instead of another question
    """

    # Canonical clinical intake domains in desired progression order
    DOMAIN_PLAN = [
        "chief_concern",
        "onset_duration",
        "severity",
        "progression",
        "modifiers",          # better/worse factors
        "red_flags",
        "medications",
        "allergies",
        "relevant_history",
    ]

    # Minimal coverage threshold to attempt concluding summary
    MIN_COVERAGE_FOR_CONCLUSION = 6

    def __init__(self, ai: AIClient | None = None) -> None:
        self.ai = ai or AIClient()

    def _init_metadata(self, conversation: Conversation) -> dict:
        """Ensure conversation.metadata has needed keys and return it."""
        meta = conversation.metadata or {}
        if "intake" not in meta or not isinstance(meta.get("intake"), dict):
            meta["intake"] = {}
        intake = meta["intake"]
        intake.setdefault("domains_asked", [])
        intake.setdefault("concluded", False)
        intake.setdefault("coverage_score", 0)
        intake.setdefault("last_domain", None)
        # track basic counters
        intake.setdefault("turns", 0)
        return meta

    def _update_coverage(self, meta: dict, next_domain: str | None) -> None:
        """Update domains_asked and coverage metrics in metadata."""
        intake = meta["intake"]
        if next_domain and next_domain not in intake["domains_asked"]:
            intake["domains_asked"].append(next_domain)
            intake["coverage_score"] = len(set(intake["domains_asked"]))
        intake["turns"] = int(intake.get("turns", 0)) + 1
        intake["last_domain"] = next_domain

    def _determine_next_domain(self, meta: dict, patient_texts: list[str]) -> str | None:
        """Choose the next domain to ask about, skipping domains inferred from patient content."""
        intake = meta["intake"]
        asked = set(intake.get("domains_asked", []))

        # Heuristic detection of already-covered domains from patient text
        joined = " ".join(patient_texts).lower()
        inferred = set()
        if any(k in joined for k in ["since", "for ", "days", "weeks", "months", "start", "began"]):
            inferred.add("onset_duration")
        if any(k in joined for k in ["1/10", "2/10", "3/10", "4/10", "5/10", "6/10", "7/10", "8/10", "9/10", "10/10", "mild", "moderate", "severe", "severity"]):
            inferred.add("severity")
        if any(k in joined for k in ["worse", "improve", "better", "relieve", "trigger"]):
            inferred.add("progression")
            inferred.add("modifiers")
        if any(k in joined for k in ["allerg", "penicillin", "sulfa", "peanut"]):
            inferred.add("allergies")
        if any(k in joined for k in ["ibuprofen", "acetaminophen", "paracetamol", "antibiotic", "inhaler", "insulin", "pill", "tablet", "dose", "mg"]):
            inferred.add("medications")
        if any(k in joined for k in ["history", "hx", "past medical", "pmh"]):
            inferred.add("relevant_history")
        if any(k in joined for k in ["chest pain", "shortness of breath", "confusion", "faint", "vision loss", "weakness on one side"]):
            inferred.add("red_flags")
        if any(k in joined for k in ["pain", "cough", "fever", "rash", "headache", "nausea", "vomit", "diarrhea", "dizzy", "sore"]):
            inferred.add("chief_concern")

        # Treat inferred as covered to avoid repeating
        effective_asked = asked.union(inferred)

        for domain in self.DOMAIN_PLAN:
            if domain not in effective_asked:
                return domain
        return None  # nothing left to ask

    def _build_dialogue(self, conversation: Conversation) -> list[dict]:
        """Convert stored messages to OpenAI-compatible dialogue turns."""
        messages = conversation.messages.all()
        dialogue: list[dict] = []
        for m in messages:
            role = "user" if m.sender == "patient" else "assistant"
            if m.text:
                dialogue.append({"role": role, "content": m.text})
        return dialogue

    def _should_conclude(self, meta: dict, next_domain: str | None) -> bool:
        """Decide whether to produce a concluding summary instead of another question."""
        intake = meta["intake"]
        coverage = int(intake.get("coverage_score", 0))
        concluded = bool(intake.get("concluded", False))
        # Conclude if coverage threshold reached or no further domains
        return (coverage >= self.MIN_COVERAGE_FOR_CONCLUSION or next_domain is None) and not concluded

    # PUBLIC_INTERFACE
    def next_follow_up(self, conversation: Conversation) -> str:
        """Return the next follow-up or a concluding summary based on conversation context.

        The conversation is converted into OpenAI-compatible chat messages:
        - Patient messages => role=user
        - Bot messages => role=assistant

        The response will be either:
        - a single concise follow-up question (ending with '?'), or
        - a 'Conclusion:' prefixed summary paragraph to wrap up the intake.
        """
        # Prepare metadata and extract patient content
        meta = self._init_metadata(conversation)
        dialogue = self._build_dialogue(conversation)
        patient_texts = [m["content"] for m in dialogue if m["role"] == "user" and m.get("content")]

        # Choose next domain to cover
        next_domain = self._determine_next_domain(meta, patient_texts)

        # If ready to conclude, instruct AI to summarize; else instruct it to ask within selected domain.
        if self._should_conclude(meta, next_domain):
            # Build a short instruction to create a conclusion. We rely on the AIClient.summarize_dialogue
            # when we want a full note, but here we ask a compact end-of-intake conclusion for chat.
            system_prompt = (
                "You are a medical intake assistant. The intake is nearly complete. "
                "Write a brief concluding summary that synthesizes the patient's main concerns, key details "
                "(onset, severity, progression, modifiers), notable medications/allergies/history, and any red flags. "
                "Keep it concise (2–4 sentences), neutral, and factual. Start with 'Conclusion:' and do not ask questions."
            )
            # We ask the regular LLM chat API (ask_follow_up path) with an explicit instruction to produce a conclusion.
            # Reuse ask_follow_up to keep provider handling consistent but override the system instruction via a tagged turn.
            # We include a control marker to bias the provider.
            control_user = {
                "role": "user",
                "content": "Compose a concluding summary now. End the conversation if appropriate."
            }
            llm_dialogue = [{"role": "system", "content": system_prompt}] + dialogue + [control_user]
            text = self.ai.ask_follow_up(dialogue=llm_dialogue)  # It will use the last 'user' content to respond

            # Mark concluded in metadata to avoid further questions
            meta["intake"]["concluded"] = True
            conversation.metadata = meta
            conversation.save(update_fields=["metadata"])
            # Ensure conclusion is prefixed in case the provider omitted it
            text = (text or "").strip()
            if text and not text.lower().startswith("conclusion"):
                text = f"Conclusion: {text}"
            return text

        # Otherwise, continue with another follow-up targeting the next domain
        domain_instruction_map = {
            "chief_concern": "Clarify the main issue and key symptoms.",
            "onset_duration": "Clarify onset and duration.",
            "severity": "Clarify severity from 1–10 and current intensity.",
            "progression": "Clarify whether symptoms are improving, worsening, or fluctuating.",
            "modifiers": "Ask about factors that make it better or worse, including triggers.",
            "red_flags": "Screen for red flags related to the symptoms (danger signs).",
            "medications": "Ask about current medications and dosages, including OTC and supplements.",
            "allergies": "Ask about medication or food allergies and reactions.",
            "relevant_history": "Ask for any relevant past medical history or related conditions.",
        }
        domain_hint = domain_instruction_map.get(next_domain or "", "Clarify the most relevant missing detail.")

        # Build domain-aware system prompt that also says NOT to repeat previous domains and to avoid repeating itself
        system_prompt = (
            "You are an empathetic clinical intake assistant. Ask exactly ONE concise question (<= 28 words) "
            "focused on the specified domain, avoiding repetition of topics already covered. "
            "Do not provide advice or multiple questions. End with a question mark.\n"
            f"Target domain: {next_domain or 'general'}\n"
            f"Domain guidance: {domain_hint}\n"
            "If the domain appears sufficiently covered in the conversation, pivot to another missing domain instead."
        )

        # Add a small steering 'user' turn to bias the model and include full dialogue
        primer = "Context summary to guide the next single question:\n"
        if patient_texts:
            last = patient_texts[-1].strip()
            primer += f"- Most recent patient message: {last}\n"
        asked_list = meta["intake"].get("domains_asked", [])
        if asked_list:
            primer += "- Domains already asked: " + ", ".join(asked_list) + "\n"

        llm_dialogue = [{"role": "system", "content": system_prompt}, {"role": "user", "content": primer}] + dialogue

        # Route via ask_follow_up with the composed dialogue containing our system + primer
        question = self.ai.ask_follow_up(dialogue=llm_dialogue).strip()
        if question and not question.endswith("?"):
            question = question.rstrip(".") + "?"

        # Update metadata coverage and persist
        self._update_coverage(meta, next_domain)
        conversation.metadata = meta
        conversation.save(update_fields=["metadata"])

        return question or "Could you share a bit more detail about your symptoms?"
