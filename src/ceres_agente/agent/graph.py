from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from ..config import get_settings
from ..prompts import SYSTEM_PROMPT
from ..tools import get_tools


def build_agent():
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.agent_model,
        temperature=settings.agent_temperature,
        api_key=settings.openai_api_key,
    )
    tools = get_tools()
    system_prompt = SYSTEM_PROMPT.format(date=date.today().isoformat())
    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent


def run_agent(query: str) -> str:
    agent = build_agent()
    result = agent.invoke({"messages": [HumanMessage(content=query)]})
    return result["messages"][-1].content
