# Patient Health Inquiry and Note Management – Backend

This Django REST API handles:
- Patient chatbot conversations (start, send, continue)
- Disease note generation from conversation content
- Saving notes as `.txt` files to local disk

Style: Ocean Professional (clean, modern, minimalist; blue/amber accents)

## Quick start

1) Environment variables
- Copy `.env.example` to `.env` and update if needed. OneDrive variables are no longer used.

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
  body: { conversation_id, sender: "patient"|"bot", text, patient_id? }
  notes:
    - If conversation_id exists, the message is appended.
    - If conversation_id does not exist and patient_id is provided, a new conversation is created for that patient and the message is appended. Response status 201.
    - If conversation_id does not exist and patient_id is not provided, 404 is returned with a helpful hint.
- POST /api/conversations/continue/
  body: { conversation_id, messages: [{sender, text}, ...] }
- GET /api/conversations/status/?conversation_id=<uuid>

Notes:
- POST /api/notes/generate/
  body: { conversation_id, note_title? }
  returns: { conversation_id, note_title, note_text }

Local Save:
- POST /api/notes/save-local/
  body: { conversation_id, note_text, filename }
  behavior: Saves .txt file to ONEDRIVE_SAVE_DIR (configurable) or fallback C:\Nilesh_TATA\Prescription. API returns success/failure details.

AI:
- POST /api/ai/next-follow-up/
  body: { conversation_id }
  returns: { conversation_id, question }

- POST /api/ai/generate-and-save-summary/
  body: { conversation_id, filename, note_title? }
  behavior: Generates an AI summary and saves it as .txt to ONEDRIVE_SAVE_DIR.

## Local Save Directory

- Files are written to: C:\Nilesh_TATA\Prescription
- The application ensures the directory exists (creates it if missing).
- Filenames will enforce a .txt extension if not provided.
- On write failure (permissions, disk, path issues), the API returns an error with details.

## Notes

- Authentication is set to AllowAny as a placeholder. Integrate with your preferred auth method in production.
- The note generation is rule-based for clarity; you can replace it with an LLM-backed summarizer.
- Error responses follow a consistent Ocean Professional payload.