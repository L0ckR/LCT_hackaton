# Review Analytics Service

MVP backend for dashboard constructor that analyzes client reviews of banking products.

## Features
- FastAPI REST API with JWT authentication
- Upload and store reviews (JSON/CSV)
- Sentiment analysis via Celery and TextBlob
- Aggregated statistics and time-series endpoints
- Dummy clustering by product
- PostgreSQL storage with SQLAlchemy and Alembic
- Dockerized with Celery worker, PostgreSQL and Redis

## Local Development

1. Copy environment file:
   ```bash
   cp .env.example .env
   ```
2. Build and start services:
   ```bash
   docker-compose up --build
   ```
3. Open API docs at [http://localhost:8000/docs](http://localhost:8000/docs)

## Running Tests

```bash
pytest
```
