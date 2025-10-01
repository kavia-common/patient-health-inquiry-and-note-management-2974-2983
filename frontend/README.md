# Patient Chatbot Frontend (Ocean Professional)

A minimal, modern chat UI that connects to the Django chatbot backend.

Features:
- Start conversation with patient_id
- Send patient messages (auto-create conversation if needed)
- Request AI follow-up question
- Generate summary (view only) or generate & save summary (shows save result)
- Configurable API base URL
- Lightweight, no build step (HTML/CSS/JS)

Quick Start:
1) Ensure backend is running (default: http://localhost:3001)
2) Open index.html in a browser (recommended: serve with a static file server if CORS setup differs)
3) Set API Base URL to http://localhost:3001/api (or your backend URL)
4) Enter Patient ID and click “Start Conversation”
5) Chat, click “Ask Follow-up”, and generate summaries

Endpoints used:
- POST /api/conversations/start/
- POST /api/conversations/send/
- GET  /api/conversations/status/?conversation_id=UUID
- POST /api/ai/next-follow-up/
- POST /api/notes/generate/
- POST /api/ai/generate-and-save-summary/

Styling:
- Ocean Professional theme (blue/amber accents, rounded corners, subtle shadows)
