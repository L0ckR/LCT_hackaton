from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
import os
from typing import List
from pydantic import BaseModel, Field
import json
from pathlib import Path
import asyncio

load_dotenv()

LLM_API_KEY = os.getenv('LLM_API_KEY')
BASE_URL = os.getenv('LLM_BASE_URL')
MODEL_NAME = os.getenv('MODEL_NAME')
class ChartJsonSchema(BaseModel):
    chart_type: str = Field(
        description="Тип графика"
    )
    columns: List[str] = Field(
        description="Колонки, необходимые для построения графика"
    )
    metric_name: str = Field(
        description='Метрика, которая будет подсчитана на графике'
    )
    aggregate_by: str = Field(description='Агрегирующая колонка, по которой будет делаться groupby')

LLM = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0,
    api_key=LLM_API_KEY,
    base_url=BASE_URL,
)

report_llm = LLM.with_structured_output(ChartJsonSchema)

SRC_DIR = Path(__file__).parent
PROMPT_PATH = SRC_DIR.parent / "data" / "prompts" / "build_md_report.md"

with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
    CHART_GEN_PROMPT = f.read()

async def generate_chart(data: str) -> dict:
    """
    Asynchronously generates a chart
    """
    messages = [
        SystemMessage(content=CHART_GEN_PROMPT),
        HumanMessage(content=data)  
    ]
    response: ChartJsonSchema = await report_llm.ainvoke(messages)
    return response.dict() 

if __name__ == '__main__':
    test_data = '''
    '''

    async def main():
        result = await generate_chart(test_data)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(main())