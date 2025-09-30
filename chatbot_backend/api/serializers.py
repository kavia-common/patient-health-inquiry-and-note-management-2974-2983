from rest_framework import serializers


# PUBLIC_INTERFACE
class StartConversationSerializer(serializers.Serializer):
    """Serializer for starting a new conversation."""
    patient_id = serializers.CharField(help_text="Unique patient identifier")
    metadata = serializers.DictField(required=False, default=dict, help_text="Optional metadata for the conversation")


# PUBLIC_INTERFACE
class MessageSerializer(serializers.Serializer):
    """Serializer for sending a message within a conversation."""
    conversation_id = serializers.UUIDField(help_text="Conversation ID")
    sender = serializers.ChoiceField(choices=["patient", "bot"], help_text="Message sender")
    text = serializers.CharField(help_text="Message content")


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
class OneDriveSaveRequestSerializer(serializers.Serializer):
    """Serializer for saving a note to OneDrive."""
    conversation_id = serializers.UUIDField(help_text="Conversation ID")
    note_text = serializers.CharField(help_text="The note text to save as .txt")
    filename = serializers.CharField(help_text="Desired filename, .txt will be enforced if not present")
    onedrive_folder_path = serializers.CharField(help_text="Target OneDrive folder path, e.g., /Documents/HealthNotes")


# PUBLIC_INTERFACE
class ConversationStatusSerializer(serializers.Serializer):
    """Serializer for conversation status info."""
    conversation_id = serializers.UUIDField()
    patient_id = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    message_count = serializers.IntegerField()
