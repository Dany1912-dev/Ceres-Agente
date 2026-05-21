from langchain_core.tools import tool


@tool
def sumar(a: float, b: float) -> float:
    """Suma dos números y devuelve el resultado."""
    return a + b


@tool
def buscar_informacion(consulta: str) -> str:
    """Busca información sobre un tema. Reemplaza con una herramienta real (DuckDuckGo, Tavily, etc.)."""
    return f"Resultado de búsqueda para '{consulta}': [conecta una herramienta de búsqueda real aquí]"


def get_tools() -> list:
    return [sumar, buscar_informacion]
