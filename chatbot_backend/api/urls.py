from django.urls import path
from .views import (
    health,
    start_conversation,
    send_message,
    continue_conversation,
    generate_note,
    save_note_to_local,
    conversation_status,
    next_follow_up,
    generate_and_save_summary,
)
from .ai_docs import ai_usage_help, ai_diagnostics

urlpatterns = [
    path('health/', health, name='Health'),
    path('ai/help/', ai_usage_help, name='AIUsageHelp'),
    path('ai/diagnostics/', ai_diagnostics, name='AIDiagnostics'),
    path('conversations/start/', start_conversation, name='StartConversation'),
    path('conversations/send/', send_message, name='SendMessage'),
    path('conversations/continue/', continue_conversation, name='ContinueConversation'),
    path('conversations/status/', conversation_status, name='ConversationStatus'),
    # Notes and AI
    path('notes/generate/', generate_note, name='GenerateNote'),
    path('notes/save-local/', save_note_to_local, name='SaveNoteToLocal'),
    path('ai/next-follow-up/', next_follow_up, name='NextFollowUp'),
    path('ai/generate-and-save-summary/', generate_and_save_summary, name='GenerateAndSaveSummary'),
]
