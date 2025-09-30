from django.urls import path
from .views import (
    health,
    start_conversation,
    send_message,
    continue_conversation,
    generate_note,
    save_note_to_onedrive,
    conversation_status,
)

urlpatterns = [
    path('health/', health, name='Health'),
    path('conversations/start/', start_conversation, name='StartConversation'),
    path('conversations/send/', send_message, name='SendMessage'),
    path('conversations/continue/', continue_conversation, name='ContinueConversation'),
    path('notes/generate/', generate_note, name='GenerateNote'),
    path('onedrive/save/', save_note_to_onedrive, name='SaveNoteToOneDrive'),
    path('conversations/status/', conversation_status, name='ConversationStatus'),
]
