"""
API app package initialization.

Exposes public interfaces for serializers and services to make imports explicit.
"""

# PUBLIC_INTERFACE
def get_app_description():
    """Return a short description of the API app."""
    return "Chatbot conversations, note generation, and OneDrive integration."

# Re-export commonly used modules (optional, for convenience)
from . import serializers as _serializers  # noqa: F401
from . import services as _services  # noqa: F401
