from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Column
from sqlalchemy import Text


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str
    telefono: str
    rfc: Optional[str] = None
    giro: str
    municipio: str
    estado: str
    monto_solicitado: float
    plazo_meses: int
    tipo_credito: str
    tipo_persona: str = "fisica"
    score: Optional[float] = None
    decision: Optional[str] = None
    elegible_fira: Optional[bool] = None
    programa_fira: Optional[str] = None
    tasa_final: Optional[float] = None
    cuota_mensual: Optional[float] = None
    status: str = "nuevo"
    creado_en: datetime = Field(default_factory=datetime.utcnow)


class Conversacion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    telefono: str = Field(index=True, unique=True)
    estado: str = "inicio"
    historial: Optional[str] = Field(default="[]", sa_column=Column(Text))
    datos_recolectados: Optional[str] = Field(default="{}", sa_column=Column(Text))
    actualizado_en: datetime = Field(default_factory=datetime.utcnow)


class Cotizacion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    telefono: str
    monto: float
    plazo_meses: int
    tipo_credito: str
    tasa_tiie: float
    spread: float
    tasa_final: float
    cuota_mensual: float
    creado_en: datetime = Field(default_factory=datetime.utcnow)
