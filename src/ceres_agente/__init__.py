"""KronoFinanzas Ceres — Agente Inteligente de Ventas para Grupo Ceres.

Arquitectura multi-agente con 6 subagentes especializados:
- FIRA (RAG normativo)
- Cotizador (TIIE + spread)
- Scoring (ML RandomForest)
- Documentos (gestion de papeleria)
- Seguimiento (estatus de solicitudes)
- Insights (reportes para gerentes)
"""

from .agent import build_agent, run_agent

__all__ = ["build_agent", "run_agent"]
