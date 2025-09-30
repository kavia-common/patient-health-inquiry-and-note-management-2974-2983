from rest_framework import serializers


# PUBLIC_INTERFACE
class StartConversationSerializer(serializers.Serializer):
    """Serializer for starting a new conversation."""
    patient_id = serializers.CharField(help_text="Unique patient identifier")
    metadata = serializers.DictField(required=False, default=dict, help_text="Optional metadata for the conversation")


# PUBLIC_INTERFACE
class MessageSerializer(serializers.Serializer):
    """Serializer for sending a message within a conversation.
    
    Behavior:
    - If conversation_id references an existing conversation, the message will be appended.
    - If the conversation does not exist and patient_id is provided, a new conversation will be created
      for that patient and the message appended.
    - If the conversation does not exist and patient_id is not provided, the request will be rejected.
    """
    conversation_id = serializers.UUIDField(help_text="Conversation ID")
    sender = serializers.ChoiceField(choices=["patient", "bot"], help_text="Message sender")
    text = serializers.CharField(help_text="Message content")
    patient_id = serializers.CharField(required=False, allow_blank=False, help_text="Patient ID to create a conversation if conversation_id is not found")


# PUBLIC_INTERFACE
class ContinueConversationSerializer(serializers.Serializer):
    """Serializer to continue a conversation by appending new messages."""
    conversation_id = serializers.UUIDField(help_text="Conversation ID")
    messages = MessageSerializer(many=True, help_text="List of messages to append")


# PUBLIC_INTERFACE
class GenerateNoteRequestSerializer(serializers.Serializer):
    """Serializer for generating a disease note from a conversation."""
    conversation_id = serializers.UUIDField(help_text="Conversation ID")
    note_title = serializers.CharField(required=False, allow_blank=True, default="", help_text="Optional title for the note")


# PUBLIC_INTERFACE
class GenerateNoteResponseSerializer(serializers.Serializer):
    """Serializer for the generated disease note response."""
    conversation_id = serializers.UUIDField()
    note_title = serializers.CharField()
    note_text = serializers.CharField()


# PUBLIC_INTERFACE
class LocalSaveRequestSerializer(serializers.Serializer):
    """Serializer for saving a note to local disk."""
    conversation_id = serializers.UUIDField(help_text="Conversation ID")
    note_text = serializers.CharField(help_text="The note text to save as .txt")
    filename = serializers.CharField(help_text="Desired filename, .txt will be enforced if not present")


# PUBLIC_INTERFACE
class ConversationStatusSerializer(serializers.Serializer):
    """Serializer for conversation status info."""
    conversation_id = serializers.UUIDField()
    patient_id = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    message_count = serializers.IntegerField()
