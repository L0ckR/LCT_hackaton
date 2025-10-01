# Агент по созданию графиков

сваггер: /docs

## Как запустить?

1) .env:

LLM_API_KEY=...

LLM_BASE_URL=...

MODEL_NAME=Qwen/Qwen3-Next-80B-A3B-Instruct

2) docker compose up


## Пример

input:

{
  "data": "нарисуй график волатильности по продуктам"
}

output:

{
  "chart_type": "bar",
  "columns": [
    "product",
    "volatility"
  ],
  "metric_name": "volatility",
  "aggregate_by": "product"
}
