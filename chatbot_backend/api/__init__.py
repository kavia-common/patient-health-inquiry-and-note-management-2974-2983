"""
API app package initialization.

Avoid importing modules that access Django models at import time to prevent
AppRegistryNotReady errors during Django startup. If you need to access
serializers or services, use the lazy accessors below.
"""

# PUBLIC_INTERFACE
def get_app_description():
    """Return a short description of the API app."""
    return "Chatbot conversations, note generation, and local note storage."

# PUBLIC_INTERFACE
def get_serializers_module():
    """Lazily import and return the serializers module."""
    from . import serializers  # Local import to avoid early app loading
    return serializers

# PUBLIC_INTERFACE
def get_services_module():
    """Lazily import and return the services module."""
    from . import services  # Local import to avoid early app loading
    return services
