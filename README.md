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


## Parser API Examples

Запросы отправляются на `POST /parser/run`. Все параметры, кроме `source`, опциональны 
- **Sravni.ru (Газпромбанк)**

  ```json
  {
    "source": "gazprombank_reviews",
    "start_date": "2024-01-01T00:00:00+00:00",
    "max_pages": 200,
    "page_size": 20,
    "min_delay": 1.0,
    "max_delay": 2.0,
    "finger_print": "1d345dd221ef718448c6bef7fc795d47",
    "output_filename": "gazprombank_reviews.csv"
  }
  ```
- **Banki.ru (Газпромбанк)**

  ```json
  {
    "source": "banki_ru",
    "start_date": "2024-01-01T00:00:00+00:00",
    "max_pages": 200,
    "page_size": 30,
    "min_delay": 1.0,
    "max_delay": 2.0,
    "output_filename": "banki_ru_reviews.csv"
  }
  ```