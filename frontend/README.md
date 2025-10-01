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

Proxy and multi-container guidance:
- When this frontend is served from a proxy path like https://<host>/proxy/8000/, it will auto-detect and default API Base to https://<host>/proxy/3001/api so calls route through the same reverse proxy to the Django backend on port 3001.
- You can always override the API Base in the UI. For proxied setups, prefer:
  - /proxy/3001/api (relative to current origin) or
  - https://<host>/proxy/3001/api
- For separate containers without a top-level proxy:
  - If the browser can reach the backend directly, use https://<backend-host>:3001/api
  - Otherwise, configure your gateway/reverse-proxy (e.g., Nginx, Traefik) to map frontend and backend under one origin to avoid CORS complications.
- CORS: The backend is configured with CORS_ALLOW_ALL_ORIGINS = True for development. In production, restrict allowed origins appropriately.
- Docs: Swagger UI served by backend is at /docs (e.g., https://<host>:3001/docs). If accessed via proxy, it should be reachable at /proxy/3001/docs.
