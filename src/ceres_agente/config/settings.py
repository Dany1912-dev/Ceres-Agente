from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    agent_model: str = "gpt-4o-mini"
    agent_temperature: float = 0.0

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "ceres-agente"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
