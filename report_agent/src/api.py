from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Union, Dict, Any
import json
from .report_agent import generate_pdf_report  

app = FastAPI()

class ChartItem(BaseModel):
    chart_name: str
    chart_data: Union[Dict[str, Union[int, float]], List[Dict[str, Any]]]
    chart_type: str

    model_config = {"populate_by_name": True}  

@app.post("/generate_report")
async def generate_report(charts: List[ChartItem]):
    try:
        charts_data = [
            {
                "chart_name": chart.chart_name,
                "chart_data": chart.chart_data,
                "chart_type": chart.chart_type
            }
            for chart in charts
        ]

        charts_json_str = json.dumps(charts_data, ensure_ascii=False)

        report = await generate_pdf_report(charts_json_str)

        return report

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Ошибка парсинга JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации отчёта: {str(e)}")