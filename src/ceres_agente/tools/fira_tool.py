import boto3
from langchain_core.tools import tool

from ..config import get_settings


def _get_bedrock_client():
    settings = get_settings()
    return boto3.client(
        service_name="bedrock-agent-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


@tool
def consultar_normativa_fira(consulta: str) -> str:
    """Consulta las reglas de operación y normativas de FIRA publicadas en el DOF.
    Úsala para responder preguntas sobre criterios de elegibilidad, montos máximos en UDIS,
    restricciones geográficas, sectores permitidos y cualquier requisito crediticio de FIRA.
    """
    settings = get_settings()
    client = _get_bedrock_client()

    response = client.retrieve(
        knowledgeBaseId=settings.aws_knowledge_base_id,
        retrievalQuery={"text": consulta},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 5,
            }
        },
    )

    resultados = response.get("retrievalResults", [])
    if not resultados:
        return "No se encontró información relevante en la normativa de FIRA para esta consulta."

    fragmentos = []
    for i, resultado in enumerate(resultados, 1):
        texto = resultado.get("content", {}).get("text", "")
        ubicacion = resultado.get("location", {})
        uri = ubicacion.get("s3Location", {}).get("uri", "DOF - Normativa FIRA")
        fragmentos.append(f"[Fuente {i} - {uri}]:\n{texto}")

    return "\n\n---\n\n".join(fragmentos)


def get_tools() -> list:
    return [consultar_normativa_fira]
