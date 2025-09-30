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
)
from .models import Conversation
from .services import ConversationManager, NoteGenerator, LocalNoteStorage, LocalNoteStorageError


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
    operation_description="Appends a single message to an existing conversation.",
    request_body=MessageSerializer,
    responses={200: openapi.Response("OK")},
    tags=["Conversations"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def send_message(request):
    """Append a single message to a conversation."""
    serializer = MessageSerializer(data=request.data)
    if not serializer.is_valid():
        return ocean_error("Invalid input", details=serializer.errors)

    cm = ConversationManager()
    try:
        cm.append_messages(
            serializer.validated_data["conversation_id"],
            [(serializer.validated_data["sender"], serializer.validated_data["text"])],
        )
    except Conversation.DoesNotExist:
        return ocean_error("Conversation not found", code="not_found", status_code=status.HTTP_404_NOT_FOUND)

    return ocean_ok({"conversation_id": str(serializer.validated_data["conversation_id"]), "appended": 1})


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
