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

class ReportJsonSchema(BaseModel):
    executive_summary: dict = Field(
        description="Сводка с ключевыми выводами и рекомендациями"
    )
    insights_by_chart: List[dict] = Field(
        description="Анализ по каждому графику"
    )

LLM = ChatOpenAI(
    model="Qwen/Qwen3-Next-80B-A3B-Instruct",
    temperature=0,
    api_key=LLM_API_KEY,
    base_url=BASE_URL,
)

report_llm = LLM.with_structured_output(ReportJsonSchema)

SRC_DIR = Path(__file__).parent
PROMPT_PATH = SRC_DIR.parent / "data" / "prompts" / "build_md_report.md"

with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
    REPORT_GEN_PROMPT = f.read()

async def generate_pdf_report(data: str) -> dict:
    """
    Asynchronously generates a structured report from chart data.
    Input `data` should be a JSON string of chart list.
    Returns a dict conforming to ReportJsonSchema.
    """
    messages = [
        SystemMessage(content=REPORT_GEN_PROMPT),
        HumanMessage(content=data)  
    ]
    response: ReportJsonSchema = await report_llm.ainvoke(messages)
    return response.dict() 

if __name__ == '__main__':
    test_data = '''[
        {
            "chart_name": "Продажи по регионам за май 2024",
            "chart_data": {
                "Москва": 1200,
                "Санкт-Петербург": 830,
                "Екатеринбург": 440,
                "Новосибирск": 390,
                "Казань": 330
            },
            "chart_type": "Столбчатый"
        },
        {
            "chart_name": "Трафик сайта по неделям",
            "chart_data": [
                {"неделя": "01-07 мая", "визиты": 3500},
                {"неделя": "08-14 мая", "визиты": 5600},
                {"неделя": "15-21 мая", "визиты": 4300},
                {"неделя": "22-28 мая", "визиты": 5200}
            ],
            "chart_type": "Линейный"
        },
        {
            "chart_name": "Доля устройств пользователей",
            "chart_data": {
                "Desktop": 62,
                "Mobile": 30,
                "Tablet": 8
            },
            "chart_type": "Круговой"
        }
    ]'''

    async def main():
        result = await generate_pdf_report(test_data)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(main())