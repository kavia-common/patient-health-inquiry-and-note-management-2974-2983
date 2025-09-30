import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

import requests
from django.utils import timezone

from .models import Conversation, Message


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
    """Generate a disease note from conversation messages using simple heuristics.

    Replace with an actual AI-based summarization if desired. This implementation
    provides a deterministic, explainable baseline suitable for demos.
    """

    # PUBLIC_INTERFACE
    def generate_note(self, conversation: Conversation, note_title: str = "") -> Tuple[str, str]:
        """Generate a note text from a conversation.
        Returns (title, text).
        """
        messages = conversation.messages.all()
        patient_lines = [m.text.strip() for m in messages if m.sender == "patient" and m.text.strip()]
        bot_lines = [m.text.strip() for m in messages if m.sender == "bot" and m.text.strip()]

        # Simple extraction heuristics
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

        title = note_title.strip() or f"Disease Note for Patient {conversation.patient_id}"

        # Compose a structured note
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
class OneDriveClient:
    """Minimal Microsoft Graph OneDrive client using OAuth2 Client Credentials or Authorization Code (env-configured)."""

    def __init__(self) -> None:
        # Environment variables (documented in .env.example)
        self.tenant_id = os.getenv("ONEDRIVE_TENANT_ID", "")
        self.client_id = os.getenv("ONEDRIVE_CLIENT_ID", "")
        self.client_secret = os.getenv("ONEDRIVE_CLIENT_SECRET", "")
        self.scope = os.getenv("ONEDRIVE_SCOPE", "https://graph.microsoft.com/.default")
        self.auth_mode = os.getenv("ONEDRIVE_AUTH_MODE", "client_credentials")  # or "authorization_code"
        self.redirect_uri = os.getenv("ONEDRIVE_REDIRECT_URI", "")

        # For delegated flow (authorization code)
        self.user_access_token = os.getenv("ONEDRIVE_USER_ACCESS_TOKEN", "")

        self.graph_base = "https://graph.microsoft.com/v1.0"

    # PUBLIC_INTERFACE
    def save_text_file(self, folder_path: str, filename: str, content: str) -> dict:
        """Save a text file to a user's OneDrive folder using Microsoft Graph.
        Returns the Graph API file item JSON.

        Note: For client_credentials, access is typically to application drives or shared drives
        with proper permissions. For user personal OneDrive, delegated access (authorization_code)
        with a user access token is required.
        """
        token = self._get_access_token()
        if not filename.lower().endswith(".txt"):
            filename = f"{filename}.txt"

        # Encode content as binary
        data = content.encode("utf-8")

        # Build upload URL
        # Using drive root special path: /me/drive/root:/path/to/file:/content
        # folder_path should start with "/" or be relative; normalize
        normalized = folder_path if folder_path.startswith("/") else f"/{folder_path}"
        upload_url = f"{self.graph_base}/me/drive/root:{normalized}/{filename}:/content"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain",
        }
        resp = requests.put(upload_url, headers=headers, data=data, timeout=60)
        if resp.status_code not in (200, 201):
            raise OneDriveError(f"OneDrive upload failed: {resp.status_code} {resp.text}")

        return resp.json()

    def _get_access_token(self) -> str:
        """Get an access token based on configured mode."""
        if self.auth_mode == "authorization_code":
            if not self.user_access_token:
                raise OneDriveError("Missing ONEDRIVE_USER_ACCESS_TOKEN for delegated access.")
            return self.user_access_token

        # Default to client credentials
        for var in ("ONEDRIVE_TENANT_ID", "ONEDRIVE_CLIENT_ID", "ONEDRIVE_CLIENT_SECRET"):
            if not os.getenv(var):
                raise OneDriveError(f"Missing environment variable: {var}")

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
            "grant_type": "client_credentials",
        }
        resp = requests.post(token_url, data=data, timeout=30)
        if resp.status_code != 200:
            raise OneDriveError(f"Failed to obtain access token: {resp.status_code} {resp.text}")
        return resp.json().get("access_token", "")


class OneDriveError(Exception):
    """OneDrive-related error."""
    pass
