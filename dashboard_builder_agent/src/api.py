# main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
import json
from .dashboard_builder import generate_chart

app = FastAPI(
    title="Chart Report Generator",
    description="API для генерации графиков на основе входных данных",
    version="1.0.0"
)

class ChartRequest(BaseModel):
    data: str  

class ChartResponse(BaseModel):
    chart_type: str
    columns: list[str]
    metric_name: str
    aggregate_by: str

@app.post("/generate-chart", response_model=ChartResponse)
async def generate_report(request: ChartRequest):

    try:
        result = await generate_chart(request.data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации отчёта: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)