"""
Authentication package.

Exposes the FastAPI dependency `get_current_user`, which any protected route
can declare as a parameter to require a valid Supabase JWT.
"""

from .auth_dependency import get_current_user, get_current_user_optional

__all__ = ["get_current_user", "get_current_user_optional"]
