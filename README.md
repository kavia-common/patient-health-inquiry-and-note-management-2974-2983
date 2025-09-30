# Patient Health Inquiry and Note Management – Backend

This Django REST API handles:
- Patient chatbot conversations (start, send, continue)
- Disease note generation from conversation content
- Saving notes as `.txt` files to OneDrive via Microsoft Graph

Style: Ocean Professional (clean, modern, minimalist; blue/amber accents)

## Quick start

1) Create and configure environment variables
- Copy `.env.example` to `.env` and fill in required OneDrive credentials (do not commit secrets).

2) Install Python dependencies
- pip install -r chatbot_backend/requirements.txt

3) Apply migrations
- python chatbot_backend/manage.py migrate

4) Run server
- python chatbot_backend/manage.py runserver 0.0.0.0:3001

Docs at:
- /docs (Swagger UI)
- /redoc (ReDoc)
- /openapi.json

## REST Endpoints

Base path: /api

Health:
- GET /api/health/

Conversations:
- POST /api/conversations/start/
  body: { patient_id, metadata? }
- POST /api/conversations/send/
  body: { conversation_id, sender: "patient"|"bot", text }
- POST /api/conversations/continue/
  body: { conversation_id, messages: [{sender, text}, ...] }
- GET /api/conversations/status/?conversation_id=<uuid>

Notes:
- POST /api/notes/generate/
  body: { conversation_id, note_title? }
  returns: { conversation_id, note_title, note_text }

OneDrive:
- POST /api/onedrive/save/
  body: { conversation_id, note_text, filename, onedrive_folder_path }

## OneDrive Configuration

Environment variables (see .env.example):
- ONEDRIVE_AUTH_MODE: client_credentials or authorization_code
- ONEDRIVE_TENANT_ID, ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET for app auth
- ONEDRIVE_SCOPE (default: https://graph.microsoft.com/.default)
- OR provide ONEDRIVE_USER_ACCESS_TOKEN for delegated access

The service uses Microsoft Graph:
- PUT https://graph.microsoft.com/v1.0/me/drive/root:{folder}/{filename}:/content
- Content-Type: text/plain

Ensure your app has appropriate Microsoft Graph permissions (Files.ReadWrite, etc.) and consent granted.

## Notes

- Authentication is set to AllowAny as a placeholder. Integrate with your preferred auth method in production.
- The note generation is rule-based for clarity; you can replace it with an LLM-backed summarizer.
- Error responses follow a consistent Ocean Professional payload.