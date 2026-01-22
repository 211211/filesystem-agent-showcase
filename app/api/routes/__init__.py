"""
API routes package.
"""

from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.stream import router as stream_router

__all__ = ["chat_router", "documents_router", "stream_router"]
