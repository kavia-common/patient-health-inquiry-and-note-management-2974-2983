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
    """Helper that uses AI to generate dynamic follow-up questions based on stored conversation."""

    def __init__(self, ai: AIClient | None = None) -> None:
        self.ai = ai or AIClient()

    # PUBLIC_INTERFACE
    def next_follow_up(self, conversation: Conversation) -> str:
        """Return the next follow-up question based on conversation context."""
        messages = conversation.messages.all()
        dialogue = []
        for m in messages:
            role = "user" if m.sender == "patient" else "assistant"
            dialogue.append({"role": role, "content": m.text})
        return self.ai.ask_follow_up(dialogue=dialogue)
