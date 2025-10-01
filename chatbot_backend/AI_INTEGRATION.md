# AI Integration Guide

This backend supports dynamic, AI-powered conversations using an LLM with optional RAG and a rule-based fallback.

Out of the box, the system works in `mock` mode (no external calls). To enable a real LLM provider, configure environment variables as below.

## Providers

- mock (default)
  - No API calls. Returns deterministic, symptom-aware follow-ups.
- openai
  - Uses OpenAI Chat Completions API via REST.
- azure_openai
  - Uses Azure OpenAI Chat Completions (deployment name provided via AI_MODEL).
- litellm
  - Uses an OpenAI-compatible proxy like LiteLLM or your own gateway.

## Environment Variables

See `.env.example` for a template. Key variables:

- AI_PROVIDER: mock | openai | azure_openai | litellm
- AI_API_KEY: Provider API key (required for non-mock)
- AI_MODEL:
  - OpenAI/LiteLLM: model name like `gpt-4o-mini`
  - Azure OpenAI: deployment name (NOT model family)
- AI_API_BASE:
  - Optional base URL override (required for Azure OpenAI, optional for OpenAI/LiteLLM)
- AZURE_OPENAI_API_VERSION:
  - Optional, default `2024-02-15-preview`

Local note save directory:
- ONEDRIVE_SAVE_DIR: Target directory to save `.txt` notes (e.g., OneDrive-synced folder)

## How AI is Used

- Follow-up question generation
  - Endpoint: POST /api/ai/next-follow-up/
  - Logic: `api.ai.AIClient.ask_follow_up()`
  - System prompt instructs an empathetic clinical intake assistant to ask a single concise question tied to context.

- Conversation summarization for clinical notes
  - Endpoints:
    - POST /api/notes/generate/
    - POST /api/ai/generate-and-save-summary/
  - Logic: `api.ai.AIClient.summarize_dialogue()`

If the AI call fails, services fall back to a rule-based summary generation (`NoteGenerator` fallback path).

## Diagnostics and No-Restart Credential Refresh

- Runtime reads: The AI client reads AI_* environment variables at call time, so you can update credentials without restarting the server.
- Use GET `/api/ai/diagnostics/` to:
  - Inspect current AI_* configuration status (missing keys, wrong base URL, etc.)
  - Perform a live connectivity check against the provider with a tiny request
  - Receive actionable hints on how to fix common issues

## Optional RAG

You can front an OpenAI-compatible RAG gateway (e.g., LiteLLM routing to a retrieval pipeline) and set:
- AI_PROVIDER=litellm
- AI_API_BASE=<your gateway base, e.g. http://rag-gateway:4000>
- AI_MODEL=<route/model name configured in your gateway>

The backend sends conversation messages as standard OpenAI Chat API payloads, so your RAG layer can perform retrieval and augmentation transparently.

## Testing Locally

1) Keep default mock mode (no keys required)
2) Start backend, then use:
   - POST /api/conversations/start/
   - POST /api/conversations/send/
   - POST /api/ai/next-follow-up/
   - POST /api/notes/generate/
   - POST /api/ai/generate-and-save-summary/
3) After setting real AI_* credentials, call:
   - GET /api/ai/diagnostics/ to verify connectivity and credentials are accepted

## Security Notes

- Do not hard-code API keys. Use environment variables.
- In production, restrict CORS and secure your gateway/proxy.
- Sanitize and limit conversation data retained if PHI/PII policies apply.
