import boto3
from datetime import date

from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from ..config import get_settings
from ..prompts import SYSTEM_PROMPT
from ..tools import get_tools


def build_agent():
    settings = get_settings()

    boto3_session = boto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )

    llm = ChatBedrock(
        model_id=settings.agent_model,
        client=boto3_session.client("bedrock-runtime"),
        model_kwargs={"temperature": settings.agent_temperature},
    )

    tools = get_tools()
    system_prompt = SYSTEM_PROMPT.format(date=date.today().isoformat())
    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent


def run_agent(query: str) -> str:
    agent = build_agent()
    result = agent.invoke({"messages": [HumanMessage(content=query)]})
    return result["messages"][-1].content
