from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="get",
    operation_id="ai_usage_help",
    operation_summary="AI usage and configuration help",
    operation_description=(
        "Provides runtime guidance on how the AI provider is configured and how to use AI endpoints.\n\n"
        "Endpoints:\n"
        "- POST /api/ai/next-follow-up/: Returns a concise AI-generated follow-up question.\n"
        "- POST /api/notes/generate/: Generates an AI-backed note (view only).\n"
        "- POST /api/ai/generate-and-save-summary/: Generates an AI note and saves it to local storage.\n\n"
        "Configuration:\n"
        "- AI_PROVIDER: mock|openai|azure_openai|litellm\n"
        "- AI_API_KEY: API key for non-mock providers\n"
        "- AI_MODEL: model or deployment name\n"
        "- AI_API_BASE: base URL override (required for Azure OpenAI)\n"
        "- ONEDRIVE_SAVE_DIR: local save directory for .txt notes\n\n"
        "See AI_INTEGRATION.md for full details."
    ),
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT))},
    tags=["AI"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def ai_usage_help(request):
    """AI usage and configuration help endpoint."""
    return Response(
        {
            "status": "success",
            "theme": "ocean-professional",
            "data": {
                "endpoints": {
                    "next_follow_up": "/api/ai/next-follow-up/",
                    "generate_note": "/api/notes/generate/",
                    "generate_and_save_summary": "/api/ai/generate-and-save-summary/",
                },
                "env": {
                    "AI_PROVIDER": "mock|openai|azure_openai|litellm",
                    "AI_API_KEY": "set when using non-mock",
                    "AI_MODEL": "model or deployment name",
                    "AI_API_BASE": "base URL override (Azure OpenAI requires it)",
                    "AZURE_OPENAI_API_VERSION": "default 2024-02-15-preview",
                    "ONEDRIVE_SAVE_DIR": "local path to save .txt notes",
                },
                "docs": "/docs",
                "readme": "chatbot_backend/AI_INTEGRATION.md",
            },
        }
    )
