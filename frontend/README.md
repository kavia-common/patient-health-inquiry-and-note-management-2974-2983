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
3) If this UI is served under a proxy path (e.g., https://<host>/proxy/8000/), the app will FORCE the API Base to /proxy/3001/api automatically. You do not need to change it.
4) If not proxied and both frontend and backend share the same origin, leave the default or set API Base to /api.
5) Enter Patient ID and click “Start Conversation”
6) Chat, click “Ask Follow-up”, and generate summaries

Endpoints used:
- POST /api/conversations/start/
- POST /api/conversations/send/
- GET  /api/conversations/status/?conversation_id=UUID
- POST /api/ai/next-follow-up/
- POST /api/notes/generate/
- POST /api/ai/generate-and-save-summary/

Styling:
- Ocean Professional theme (blue/amber accents, rounded corners, subtle shadows)

Proxy and multi-container guidance:
- Proxied default (recommended):
  - If this frontend is under a proxy path like https://<host>/proxy/8000/, the app will FORCE the API Base to https://<host>/proxy/3001/api so all calls route through the same reverse proxy to the Django backend on port 3001.
  - Overriding to any direct container/internal DNS host in the browser is not supported and will be normalized back to the proxied path to avoid CORS/mixed-content issues.
  - Preferred values:
    - /proxy/3001/api (relative to current origin), or
    - https://<host>/proxy/3001/api
- Non-proxied setups:
  - If both frontend and backend are served from the same origin, set API Base to /api.
  - If served from different origins, configure your gateway/reverse-proxy (e.g., Nginx, Traefik) to present a single origin. Direct container URLs or internal DNS names (e.g., vscode-internal-...:3001) should not be used in the browser.
- CORS: The backend enables CORS for development. In production, restrict allowed origins as appropriate.
- Docs: Swagger UI is at /docs on the backend. If accessed via proxy, use /proxy/3001/docs.
