"""Tools del agente KronoFinanzas Ceres."""

from .fira_tool import consultar_normativa_fira, get_tools as _get_fira_tools

__all__ = ["consultar_normativa_fira", "get_tools"]


def get_tools() -> list:
    """Devuelve las tools del agente (compatibilidad hacia atras)."""
    return _get_fira_tools()
