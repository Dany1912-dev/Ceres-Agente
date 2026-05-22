from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-2"
    aws_knowledge_base_id: str = ""

    agent_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    agent_temperature: float = 0.0

    sid_twilo: str = ""
    auth_token_twilo: str = ""
    numero_twilo: str = ""

    banxico_token: str = ""

    resend_api_key: str = ""
    correo_destino: str = "dualyrf@gmail.com"
    correo_remitente: str = "Ceres <contacto@dashclass.studio>"

    database_url: str = "sqlite:///ceres.db"
    cloudflare_tunnel_token: str = ""

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "ceres-agente"


@lru_cache
def get_settings() -> Settings:
    return Settings()
