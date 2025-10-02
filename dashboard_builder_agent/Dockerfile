FROM python:3.11-slim

WORKDIR /dashboard_builder

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8003

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8003"]