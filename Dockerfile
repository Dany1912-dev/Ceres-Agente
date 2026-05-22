FROM python:3.12-slim

WORKDIR /app

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copiar archivos de dependencias primero (mejor cache de layers)
COPY pyproject.toml uv.lock ./

# Instalar dependencias sin el proyecto
RUN uv sync --frozen --no-install-project

# Copiar el código fuente
COPY src/ ./src/
COPY api.py main.py ./

# Crear directorio para la base de datos SQLite
RUN mkdir -p /data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
