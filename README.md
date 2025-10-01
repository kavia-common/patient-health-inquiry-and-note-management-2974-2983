# Patient Health Inquiry and Note Management – Backend

This Django REST API handles:
- Patient chatbot conversations (start, send, continue)
- Disease note generation from conversation content
- Saving notes as `.txt` files to local disk

Style: Ocean Professional (clean, modern, minimalist; blue/amber accents)

## Quick start

1) Environment variables
- Copy `chatbot_backend/.env.example` to `chatbot_backend/.env` and update if needed.
- AI provider defaults to `mock` (no external API calls). To enable OpenAI/Azure/LiteLLM, set AI_* vars accordingly. See `chatbot_backend/AI_INTEGRATION.md`.

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

Frontend + Proxy note:
- When the frontend is served under a proxy path (e.g., https://<host>/proxy/8000/), the frontend automatically forces API Base to /proxy/3001/api. This ensures browser requests traverse the same reverse proxy and avoids CORS/mixed-content issues.
- Do not use direct container URLs or internal DNS names in the browser (e.g., vscode-internal-...:3001). If you need cross-origin access, configure your gateway/proxy to present both frontend and backend under one origin.

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
    - After saving the message, the backend automatically generates an AI follow-up based on conversation state and returns it as `ai_follow_up.question`. It avoids repeating domains and advances through an intake plan; once sufficient info is gathered, it returns a concluding summary (`ai_follow_up.conclusion=true`) instead of another question. On failure, an `ai_error` is included and the user message remains saved.
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