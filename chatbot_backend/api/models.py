from django.db import models
import uuid


class Conversation(models.Model):
    """Stores a patient conversation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient_id = models.CharField(max_length=255, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def message_count(self) -> int:
        return self.messages.count()

    def __str__(self) -> str:
        return f"Conversation({self.id}) - patient:{self.patient_id}"


class Message(models.Model):
    """Stores individual messages belonging to a conversation."""
    SENDER_CHOICES = (
        ("patient", "Patient"),
        ("bot", "Bot"),
    )

    id = models.BigAutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, related_name="messages", on_delete=models.CASCADE)
    sender = models.CharField(max_length=16, choices=SENDER_CHOICES)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self) -> str:
        return f"Message({self.id}) {self.sender}"
