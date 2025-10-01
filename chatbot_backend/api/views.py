from uuid import UUID

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .serializers import (
    StartConversationSerializer,
    MessageSerializer,
    ContinueConversationSerializer,
    GenerateNoteRequestSerializer,
    GenerateNoteResponseSerializer,
    LocalSaveRequestSerializer,
    ConversationStatusSerializer,
    NextFollowUpRequestSerializer,
    NextFollowUpResponseSerializer,
    GenerateAndSaveSummaryRequestSerializer,
)
from .models import Conversation
from .services import (
    ConversationManager,
    NoteGenerator,
    LocalNoteStorage,
    LocalNoteStorageError,
    AIConversationHelper,
)


def ocean_ok(data: dict, status_code=status.HTTP_200_OK):
    """Ocean Professional styled success payload."""
    return Response(
        {"status": "success", "theme": "ocean-professional", "data": data},
        status=status_code,
    )


def ocean_error(message: str, code: str = "error", details: dict | None = None, status_code=status.HTTP_400_BAD_REQUEST):
    """Ocean Professional styled error payload."""
    return Response(
        {
            "status": "error",
            "theme": "ocean-professional",
            "error": {"code": code, "message": message, "details": details or {}},
        },
        status=status_code,
    )


@swagger_auto_schema(
    method="get",
    operation_id="health",
    operation_summary="Health check",
    operation_description="Returns status of the backend service.",
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT))},
    tags=["Health"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Health check endpoint to verify service availability."""
    return ocean_ok({"message": "Server is up!"})


@swagger_auto_schema(
    method="post",
    operation_id="start_conversation",
    operation_summary="Start a new conversation",
    operation_description="Creates a new conversation for a patient.",
    request_body=StartConversationSerializer,
    responses={201: openapi.Response("Created")},
    tags=["Conversations"],
)
@api_view(["POST"])
@permission_classes([AllowAny])  # Placeholder for real auth
def start_conversation(request):
    """Start a new patient conversation."""
    serializer = StartConversationSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

    cm = ConversationManager()
    convo = cm.start_conversation(serializer.validated_data["patient_id"], serializer.validated_data.get("metadata"))

    return ocean_ok(
        {
            "conversation_id": str(convo.id),
            "patient_id": convo.patient_id,
            "created_at": convo.created_at,
            "updated_at": convo.updated_at,
        },
        status_code=status.HTTP_201_CREATED,
    )


@swagger_auto_schema(
    method="post",
    operation_id="send_message",
    operation_summary="Send a single message",
    operation_description=(
        "Appends a single message to an existing conversation. "
        "If the provided conversation_id does not match an existing conversation and a patient_id is provided in the body, "
        "a new conversation will be created for that patient and the message appended. "
        "If conversation_id is invalid or not found and patient_id is not provided, a 404 error is returned.\n\n"
        "Additionally, this endpoint will automatically generate an AI-powered follow-up question based on the updated "
        "conversation and return it in the same response. On success, the bot follow-up is also saved into the conversation.\n\n"
        "Response fields:\n"
        "- conversation_id: UUID string of the active conversation\n"
        "- appended: number of patient messages appended (always 1)\n"
        "- created_new_conversation: boolean indicating if a new conversation was created\n"
        "- ai_follow_up: { question: string, saved: boolean } when AI generation succeeds\n"
        "- ai_error: { message: string, hints: string[] } when AI generation fails (patient message still saved)"
    ),
    request_body=MessageSerializer,
    responses={
        200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT)),
        201: openapi.Response("Created (new conversation created and message appended)", schema=openapi.Schema(type=openapi.TYPE_OBJECT)),
        400: openapi.Response("Validation Error"),
        404: openapi.Response("Conversation Not Found"),
    },
    tags=["Conversations"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def send_message(request):
    """
    Append a single message to a conversation and automatically generate a bot follow-up.

    PUBLIC_INTERFACE
    This is the primary chat entrypoint. After saving the user's message, the backend uses the
    configured AI provider to generate a concise follow-up question and persists it as a bot message.

    Behavior:
    - If conversation exists: append patient message, then generate and save AI follow-up.
    - If conversation does not exist and patient_id provided: create conversation, append message, then generate and save AI follow-up.
    - Otherwise: return 404 with guidance.

    Returns a success payload even if AI generation fails; in that case, includes an ai_error with hints.
    """
    serializer = MessageSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    cm = ConversationManager()
    conversation_id = serializer.validated_data["conversation_id"]
    sender = serializer.validated_data["sender"]
    text = serializer.validated_data["text"]
    patient_id = serializer.validated_data.get("patient_id")

    created = False
    status_code = status.HTTP_200_OK

    try:
        # Append patient message to existing conversation
        cm.append_messages(conversation_id, [(sender, text)])
        convo = cm.get_conversation(conversation_id)
    except Conversation.DoesNotExist:
        # Create new conversation if patient_id is provided
        if patient_id:
            convo = cm.start_conversation(patient_id=patient_id, metadata={})
            cm.append_messages(convo.id, [(sender, text)])
            created = True
            status_code = status.HTTP_201_CREATED
        else:
            return ocean_error(
                "Conversation not found",
                code="not_found",
                details={
                    "hint": "Provide a valid existing conversation_id or include patient_id to create a new conversation automatically.",
                },
                status_code=status.HTTP_404_NOT_FOUND,
            )

    # After appending the patient's message, generate AI follow-up and save it
    ai_payload = {}
    try:
        helper = AIConversationHelper()
        raw_text = helper.next_follow_up(convo)
        bot_text = (raw_text or "").strip()

        # Surface actual LLM output in UI even if it's empty/null.
        payload_follow = {"question": bot_text, "saved": False}
        if bot_text.lower().startswith("conclusion"):
            payload_follow["conclusion"] = True

        if bot_text:
            # Persist bot message so the conversation reflects the AI follow-up or conclusion
            cm.append_messages(convo.id, [("bot", bot_text)])
            payload_follow["saved"] = True
            ai_payload = {"ai_follow_up": payload_follow}
        else:
            # Provide diagnostics hints when response is empty, but keep success flow.
            ai_payload = {
                "ai_follow_up": payload_follow,
                "ai_error": {
                    "message": "AI returned an empty response.",
                    "hints": [
                        "If using a real provider, verify AI_MODEL supports chat completions.",
                        "Consider using mock provider to validate flow without external calls.",
                        "Check /api/ai/diagnostics/ for configuration and connectivity.",
                    ],
                }
            }
    except Exception as e:
        # Do not fail the entire request; return a helpful error and keep patient message appended.
        ai_payload = {
            "ai_follow_up": {"question": "", "saved": False},
            "ai_error": {
                "message": str(e),
                "hints": [
                    "Ensure AI_PROVIDER is set to openai|azure_openai|litellm (or keep 'mock' for offline).",
                    "Set AI_API_KEY for non-mock providers.",
                    "Set AI_MODEL (model name or Azure deployment name).",
                    "If using Azure, set AI_API_BASE and optionally AZURE_OPENAI_API_VERSION.",
                    "Use GET /api/ai/diagnostics/ to validate connectivity and credentials live.",
                ],
            }
        }

    return ocean_ok(
        {
            "conversation_id": str(convo.id),
            "appended": 1,
            "created_new_conversation": created,
            **ai_payload,
        },
        status_code=status_code,
    )


@swagger_auto_schema(
    method="post",
    operation_id="continue_conversation",
    operation_summary="Append multiple messages",
    operation_description="Appends multiple messages to an existing conversation.",
    request_body=ContinueConversationSerializer,
    responses={200: openapi.Response("OK")},
    tags=["Conversations"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def continue_conversation(request):
    """Append multiple messages to a conversation."""
    serializer = ContinueConversationSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    cm = ConversationManager()
    try:
        msgs = [(m["sender"], m["text"]) for m in serializer.validated_data["messages"]]
        cm.append_messages(serializer.validated_data["conversation_id"], msgs)
    except Conversation.DoesNotExist:
        return ocean_error("Conversation not found", code="not_found", status_code=status.HTTP_404_NOT_FOUND)

    return ocean_ok({"conversation_id": str(serializer.validated_data["conversation_id"]), "appended": len(msgs)})


@swagger_auto_schema(
    method="post",
    operation_id="generate_note",
    operation_summary="Generate a disease note",
    operation_description="Generates a disease note based on a conversation's messages.",
    request_body=GenerateNoteRequestSerializer,
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT))},
    tags=["Notes"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def generate_note(request):
    """Generate a disease note from the conversation content."""
    serializer = GenerateNoteRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    cm = ConversationManager()
    ng = NoteGenerator()
    try:
        convo = cm.get_conversation(serializer.validated_data["conversation_id"])
    except Conversation.DoesNotExist:
        return ocean_error("Conversation not found", code="not_found", status_code=status.HTTP_404_NOT_FOUND)

    title, note_text = ng.generate_note(convo, serializer.validated_data.get("note_title", ""))
    resp = GenerateNoteResponseSerializer(
        data={"conversation_id": str(convo.id), "note_title": title, "note_text": note_text}
    )
    resp.is_valid(raise_exception=True)
    return ocean_ok(resp.data)


@swagger_auto_schema(
    method="post",
    operation_id="next_follow_up",
    operation_summary="AI: Get next follow-up question",
    operation_description="Returns a concise AI-generated follow-up question based on the conversation context.",
    request_body=NextFollowUpRequestSerializer,
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT))},
    tags=["AI"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def next_follow_up(request):
    """Return an AI-generated follow-up question based on conversation context."""
    serializer = NextFollowUpRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    cm = ConversationManager()
    helper = AIConversationHelper()
    try:
        convo = cm.get_conversation(serializer.validated_data["conversation_id"])
        question_raw = helper.next_follow_up(convo)
        question = (question_raw or "").strip()
        resp = NextFollowUpResponseSerializer(
            data={"conversation_id": str(convo.id), "question": question}
        )
        resp.is_valid(raise_exception=True)
        return ocean_ok(resp.data)
    except Conversation.DoesNotExist:
        return ocean_error("Conversation not found", code="not_found", status_code=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        # Provide actionable hints for common misconfigurations
        return ocean_error(
            "AI follow-up generation failed",
            details={
                "detail": str(e),
                "hints": [
                    "Ensure AI_PROVIDER is set to openai|azure_openai|litellm (or keep 'mock' for offline').",
                    "Set AI_API_KEY for non-mock providers.",
                    "Set AI_MODEL (model name or Azure deployment name).",
                    "If using Azure, set AI_API_BASE and optionally AZURE_OPENAI_API_VERSION.",
                    "Use GET /api/ai/diagnostics/ to validate connectivity and credentials live.",
                ],
            },
            status_code=500,
        )


@swagger_auto_schema(
    method="post",
    operation_id="generate_and_save_summary",
    operation_summary="AI: Generate and save clinical note",
    operation_description="Generates an AI clinical note/summary from the conversation and saves it as a .txt file in the configured OneDrive directory.",
    request_body=GenerateAndSaveSummaryRequestSerializer,
    responses={
        200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT)),
        400: openapi.Response("Bad Request"),
        404: openapi.Response("Not Found"),
        500: openapi.Response("Server Error"),
    },
    tags=["AI", "Local Storage"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def generate_and_save_summary(request):
    """Generate AI summary for a conversation and save it to the configured OneDrive directory (.txt).

    Environment:
    - ONEDRIVE_SAVE_DIR must point to a local path synced to OneDrive.
    - AI_* env vars configure the AI provider.

    Returns:
      - { conversation_id, note_title, save_result: { path, bytes_written, filename } }
    """
    serializer = GenerateAndSaveSummaryRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    cm = ConversationManager()
    ng = NoteGenerator()
    storage = LocalNoteStorage()

    try:
        convo = cm.get_conversation(serializer.validated_data["conversation_id"])
    except Conversation.DoesNotExist:
        return ocean_error("Conversation not found", code="not_found", status_code=status.HTTP_404_NOT_FOUND)

    try:
        title, note_text = ng.generate_note(convo, serializer.validated_data.get("note_title", ""))
        filename = serializer.validated_data["filename"]
        result = storage.save_text_file(filename=filename, content=note_text)
        return ocean_ok(
            {
                "conversation_id": str(convo.id),
                "note_title": title,
                "save_result": result,
            }
        )
    except LocalNoteStorageError as e:
        return ocean_error(str(e), code="local_save_error", status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return ocean_error(
            "AI summary generation or save failed",
            details={
                "detail": str(e),
                "hints": [
                    "Verify AI_* environment variables (AI_PROVIDER, AI_API_KEY, AI_MODEL, AI_API_BASE for Azure).",
                    "Try GET /api/ai/diagnostics/ to test connectivity and credentials.",
                    "Check local save directory (ONEDRIVE_SAVE_DIR or legacy path) permissions if save step failed.",
                ],
            },
            status_code=500,
        )


@swagger_auto_schema(
    method="post",
    operation_id="save_note_to_local",
    operation_summary="Save a note to local disk",
    operation_description="Saves a .txt file to the local folder C:\\Nilesh_TATA\\Prescription on the host machine.",
    request_body=LocalSaveRequestSerializer,
    responses={
        200: openapi.Response("OK"),
        400: openapi.Response("Bad Request"),
        500: openapi.Response("Server Error"),
    },
    tags=["Local Storage"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def save_note_to_local(request):
    """Save provided note text as a .txt file to local disk at C:\\Nilesh_TATA\\Prescription.

    Returns:
      - On success: { path, bytes_written, filename }
      - On failure: error payload with details
    """
    serializer = LocalSaveRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    storage = LocalNoteStorage()
    try:
        result = storage.save_text_file(
            filename=serializer.validated_data["filename"],
            content=serializer.validated_data["note_text"],
        )
        return ocean_ok({"save_result": result})
    except LocalNoteStorageError as e:
        return ocean_error(str(e), code="local_save_error", status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return ocean_error("Unexpected error while saving locally", details={"detail": str(e)}, status_code=500)


@swagger_auto_schema(
    method="get",
    operation_id="conversation_status",
    operation_summary="Get conversation status",
    operation_description="Fetch basic info about a conversation including message count.",
    manual_parameters=[
        openapi.Parameter(
            "conversation_id",
            openapi.IN_QUERY,
            description="Conversation ID (UUID)",
            type=openapi.TYPE_STRING,
            required=True,
        )
    ],
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_OBJECT))},
    tags=["Conversations"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def conversation_status(request):
    """Get conversation info and message count."""
    cid = request.query_params.get("conversation_id")
    if not cid:
        return ocean_error("conversation_id is required", code="validation_error")
    try:
        convo = Conversation.objects.get(id=UUID(cid))
    except Exception:
        return ocean_error("Conversation not found", code="not_found", status_code=status.HTTP_404_NOT_FOUND)

    payload = ConversationStatusSerializer(
        {
            "conversation_id": str(convo.id),
            "patient_id": convo.patient_id,
            "created_at": convo.created_at,
            "updated_at": convo.updated_at,
            "message_count": convo.message_count(),
        }
    ).data
    return ocean_ok(payload)
