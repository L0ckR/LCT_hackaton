import json
import logging
import re
import textwrap
from typing import Iterable, List, Dict, Any
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.parser import PagePayload, ParsedReview
from app.services.openai_client import create_chat_completion

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 50000  
_CHUNK_OVERLAP = 2000  
_OUTPUT_FILE = "parsed_reviews.json"

_SYSTEM_PROMPT = (
    "Ты эксперт по анализу отзывов о банковских продуктах. "
    "Тебе нужно аккуратно извлекать структурированные данные из фрагмента текста страницы. "
    "Отвечай строго в формате валидного JSON без пояснений и комментариев."
)

_RESPONSE_STRUCTURE_HINT = (
    '{"reviews": [ { "url": "...", "review_tag": "...", "date_review": "...", '
    '"user_name": "...", "user_city": "...", "review_title": "...", "review_text": "...", '
    '"review_status": "...", "rating": "строка", "bank_name": "...", "source": "..." } ]}'
)

class ParserError(Exception):
    """Raised when the review parser fails to extract data."""

class ReviewDataset:
    """Класс для управления датасетом отзывов"""
    
    def __init__(self, output_file: str = _OUTPUT_FILE):
        self.output_file = Path(output_file)
        self.data = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "total_pages": 0,
                "total_reviews": 0,
                "pages": []
            },
            "reviews": []
        }
        self._load_existing()
    
    def _load_existing(self):
        """Загружает существующие данные"""
        if self.output_file.exists():
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                logger.info(f"Загружены существующие данные: {len(self.data.get('reviews', []))} отзывов")
            except Exception as e:
                logger.warning(f"Не удалось загрузить существующие данные: {e}")
    
    def add_page_results(self, url: str, reviews: List[ParsedReview], chunks_processed: int):
        """Добавляет результаты обработки страницы"""
        # Обновляем метаданные
        self.data["metadata"]["total_pages"] += 1
        self.data["metadata"]["total_reviews"] += len(reviews)
        self.data["metadata"]["pages"].append({
            "url": url,
            "processed_at": datetime.now().isoformat(),
            "reviews_found": len(reviews),
            "chunks_processed": chunks_processed
        })
        
        for review in reviews:
            review_dict = review.model_dump()
            # Преобразуем HttpUrl в строку если есть
            if 'url' in review_dict and hasattr(review_dict['url'], '__str__'):
                review_dict['url'] = str(review_dict['url'])
            self.data["reviews"].append(review_dict)
        
        logger.info(f"Добавлено {len(reviews)} отзывов с {url}")
    
    def save(self):
        """Сохраняет данные в JSON файл"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        logger.info(f"Данные сохранены в {self.output_file}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику датасета"""
        return {
            "total_pages": self.data["metadata"]["total_pages"],
            "total_reviews": self.data["metadata"]["total_reviews"],
            "output_file": str(self.output_file)
        }

def _clean_html(content: str) -> str:
    """МАКСИМАЛЬНО ПРОСТАЯ очистка - только убираем скрипты"""
    logger.debug(f"Начинаем очистку HTML контента длиной {len(content)} символов")
    soup = BeautifulSoup(content, "html.parser")
    
    # Убираем ТОЛЬКО скрипты, оставляем ВСЕ остальное
    for tag in soup(["script"]):
        tag.decompose()
    
    # Получаем ВЕСЬ текст как есть
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    
    logger.info(f"Очищенный текст длиной {len(text)} символов")
    logger.info(f"ВЕСЬ ТЕКСТ СТРАНИЦЫ (первые 5000 символов): {text[:5000]}")
    logger.info(f"ВЕСЬ ТЕКСТ СТРАНИЦЫ (последние 5000 символов): {text[-5000:]}")
    
    return text

def _split_into_chunks(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> List[str]:
    """Разбивает текст на чанки с перекрытием"""
    logger.info(f"Начинаем разбивку текста длиной {len(text)} символов на чанки размером {chunk_size}")
    
    if len(text) <= chunk_size:
        logger.info("Текст помещается в один чанк")
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        if end >= len(text):
            chunk = text[start:]
            chunks.append(chunk)
            logger.info(f"Последний чанк {len(chunks)}: {len(chunk)} символов")
            break
            
        # Ищем ближайший разрыв предложения или абзаца
        chunk_end = end
        for delimiter in ['\n\n', '. ', '! ', '? ']:
            last_delim = text[:end].rfind(delimiter)
            if last_delim > start:
                chunk_end = last_delim + len(delimiter)
                break
        
        chunk = text[start:chunk_end]
        chunks.append(chunk)
        logger.info(f"Чанк {len(chunks)}: {len(chunk)} символов, начало: {start}, конец: {chunk_end}")
        logger.info(f"ПЕРВЫЕ 200 СИМВОЛОВ ЧАНКА {len(chunks)}: {chunk[:200]}")
        
        start = chunk_end - overlap
        
        if start < 0:
            start = 0
    
    logger.info(f"Текст разбит на {len(chunks)} чанков")
    return chunks

async def _fetch_content(url: str) -> str:
    """Загружает контент по URL"""
    logger.info(f"Загружаем контент с URL: {url}")
    
    # Пробуем разные User-Agent для обхода блокировок
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        content = response.text
        
        # Ищем API endpoints для отзывов в HTML
        api_patterns = [
            r'api[^"\']*reviews?[^"\']*',
            r'reviews?[^"\']*api[^"\']*',
            r'/[^"\']*reviews?[^"\']*\.json',
            r'/[^"\']*reviews?[^"\']*\.js',
        ]
        
        for pattern in api_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                logger.info(f"Найдены возможные API endpoints: {matches[:5]}")
        
        logger.info(f"Получен контент длиной {len(content)} символов с {url}")
        return content

def _extract_json_block(payload: str) -> dict:
    """Извлекает JSON из ответа LLM"""
    if not payload:
        raise ParserError("Empty LLM response")
    
    logger.debug(f"Извлекаем JSON из ответа LLM: {payload[:200]}...")
    content = payload.strip()
    
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9]*", "", content)
        content = re.sub(r"```$", "", content).strip()
    
    json_patterns = [
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        r'\{.*?"reviews".*?\}',
        r'\{.*?\}',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                cleaned_match = match.strip()
                if cleaned_match.count('"') % 2 != 0:
                    cleaned_match = re.sub(r'"[^"]*$', '"', cleaned_match)
                
                if cleaned_match.endswith(','):
                    cleaned_match = cleaned_match.rstrip(',')
                
                cleaned_match = re.sub(r',\s*}', '}', cleaned_match)
                cleaned_match = re.sub(r',\s*]', ']', cleaned_match)
                
                result = json.loads(cleaned_match)
                if isinstance(result, dict) and 'reviews' in result:
                    logger.info(f"Успешно распарсен JSON с {len(result.get('reviews', []))} отзывами")
                    return result
            except json.JSONDecodeError:
                continue
    
    # Fallback обработка
    try:
        start_idx = content.find('{')
        if start_idx == -1:
            raise ParserError("LLM response does not contain JSON")
        
        brace_count = 0
        end_idx = start_idx
        for i, char in enumerate(content[start_idx:], start_idx):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        json_str = content[start_idx:end_idx + 1]
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        result = json.loads(json_str)
        logger.info(f"JSON исправлен и распарсен с {len(result.get('reviews', []))} отзывами")
        return result
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Не удалось распарсить JSON: {e}")
        raise ParserError(f"LLM response does not contain valid JSON: {e}")

def _default_source(url: str) -> str | None:
    """Извлекает источник из URL"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    host = host.lstrip("www.")
    return host or None

async def _run_llm_chunk(url: str, chunk: str, chunk_index: int, total_chunks: int) -> dict:
    """Обрабатывает один чанк через LLM"""
    if not settings.FOUNDATION_API_KEY:
        raise ParserError("FOUNDATION_API_KEY is not configured")
    
    logger.info(f"Отправляем чанк {chunk_index + 1}/{total_chunks} в LLM для URL: {url}")
    logger.info(f"РАЗМЕР ЧАНКА: {len(chunk)} символов")
    logger.info(f"ПЕРВЫЕ 500 СИМВОЛОВ ЧАНКА: {chunk[:500]}")
    logger.info(f"ПОСЛЕДНИЕ 500 СИМВОЛОВ ЧАНКА: {chunk[-500:]}")
    
    prompt_template = textwrap.dedent(
        '''
        Ты получил фрагмент #{chunk_num} из {total_chunks} со страницы {url}.
        
        КРИТИЧЕСКИ ВАЖНО: Найди ВСЕ отзывы пользователей о банковских услугах в этом фрагменте!
        
        ИЩИ ВСЕ:
        - Отзывы о банках, кредитах, депозитах, картах, ипотеке
        - Комментарии с оценками (звезды, баллы, рейтинги)
        - Мнения клиентов о банковских услугах
        - Тексты где люди делятся опытом использования банковских продуктов
        - Любые упоминания банков с отзывами
        - Даже короткие комментарии типа "хороший банк" или "плохое обслуживание"
        
        ВАЖНО: Если в тексте есть упоминания отзывов, но сами отзывы не видны, 
        попробуй извлечь хотя бы названия банков и общую информацию!
        
        Для каждого найденного отзыва собери поля: url, review_tag, date_review, user_name, 
        user_city, review_title, review_text, review_status, rating, bank_name, source.
        
        ПРАВИЛА:
        - Все поля строки, включая rating ("5", "4.5", "1")
        - Если данных нет, ставь null
        - Не придумывай данных
        - URL отзыва = {url}
        - source = домен сайта
        
        Отвечай строго JSON: {structure}
        
        Фрагмент текста:
        """{text}"""
        '''
    ).strip()
    
    user_prompt = prompt_template.format(
        chunk_num=chunk_index + 1,
        total_chunks=total_chunks,
        url=url,
        structure=_RESPONSE_STRUCTURE_HINT,
        text=chunk,
    )
    
    logger.info(f"ПОЛНЫЙ ПРОМПТ ДЛЯ LLM (первые 1000 символов): {user_prompt[:1000]}")
    
    try:
        completion = await create_chat_completion(
            model=settings.FOUNDATION_CHAT_MODEL,
            temperature=0.0,
            top_p=0.9,
            max_tokens=20000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        logger.info(f"Получен ответ от LLM для чанка {chunk_index + 1}")
    except (APIConnectionError, APITimeoutError, APIStatusError, RateLimitError) as exc:
        logger.warning(f"LLM request failed for chunk {chunk_index + 1}: %s", exc)
        raise ParserError("LLM request failed") from exc
    
    message = completion.choices[0].message.content if completion.choices else ""
    if not message:
        raise ParserError(f"LLM returned empty response for chunk {chunk_index + 1}")
    
    logger.info(f"СЫРОЙ ОТВЕТ ОТ LLM: {message}")
    
    return _extract_json_block(message)

def _coerce_reviews(raw: dict, page: PagePayload) -> List[ParsedReview]:
    """Валидирует и преобразует отзывы"""
    items = raw.get("reviews") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    
    reviews: List[ParsedReview] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
            
        payload = dict(item)
        if "url" not in payload or not payload["url"]:
            payload["url"] = str(page.url)
        if "url" in payload:
            payload["url"] = str(payload["url"])
        
        payload.setdefault("source", _default_source(str(page.url)))
        
        if "rating" in payload and payload["rating"] is not None:
            payload["rating"] = str(payload["rating"])
        
        string_fields = ["review_tag", "user_name", "user_city", "review_title",
                        "review_text", "review_status", "bank_name", "date_review"]
        for field in string_fields:
            if field in payload and payload[field] is not None:
                payload[field] = str(payload[field])
        
        try:
            review = ParsedReview.model_validate(payload)
            reviews.append(review)
        except ValidationError as exc:
            logger.warning("Validation failed for review #%s: %s", index, exc)
            continue
    
    return reviews

async def extract_reviews(pages: Iterable[PagePayload], output_file: str = _OUTPUT_FILE) -> List[ParsedReview]:
    """Извлекает отзывы из страниц с chunking и сохранением"""
    logger.info("Начинаем извлечение отзывов с chunking")
    dataset = ReviewDataset(output_file)

    pages_list = list(pages)
    logger.info(f"Получено {len(pages_list)} страниц для обработки")

    all_reviews: List[ParsedReview] = []

    for i, page in enumerate(pages_list, 1):
        logger.info(f"Обрабатываем страницу {i}/{len(pages_list)}: {page.url}")
        
        try:
            # Загрузка контента
            if page.content and len(page.content.strip()) > 100:
                html = page.content
            else:
                html = await _fetch_content(str(page.url))
            
            # Очистка - получаем ВЕСЬ текст
            cleaned = _clean_html(html)
            logger.info(f"Очищенный контент длиной {len(cleaned)} символов")
            
            # Разбивка на чанки - БЕЗ ВСЕХ ПРОВЕРОК
            chunks = _split_into_chunks(cleaned)
            logger.info(f"Страница разбита на {len(chunks)} чанков")
            
            page_reviews: List[ParsedReview] = []
            
            # Обработка каждого чанка
            for chunk_idx, chunk in enumerate(chunks):
                try:
                    logger.info(f"Обрабатываем чанк {chunk_idx + 1}/{len(chunks)} (размер: {len(chunk)})")
                    logger.info(f"СОДЕРЖИМОЕ ЧАНКА {chunk_idx + 1} (ПОЛНЫЙ ТЕКСТ): {chunk}")
                    
                    llm_payload = await _run_llm_chunk(str(page.url), chunk, chunk_idx, len(chunks))
                    logger.info(f"LLM вернул: {llm_payload}")
                    
                    chunk_reviews = _coerce_reviews(llm_payload, page)
                    logger.info(f"После валидации из чанка {chunk_idx + 1}: {len(chunk_reviews)} отзывов")
                    
                    if chunk_reviews:
                        page_reviews.extend(chunk_reviews)
                        logger.info(f"Из чанка {chunk_idx + 1} извлечено {len(chunk_reviews)} отзывов")
                        for i, review in enumerate(chunk_reviews):
                            logger.info(f"Отзыв {i+1} из чанка {chunk_idx + 1}: {review.review_text[:100]}...")
                    else:
                        logger.info(f"Чанк {chunk_idx + 1} не содержал отзывов")
                    
                except Exception as exc:
                    logger.error(f"Ошибка обработки чанка {chunk_idx + 1}: {exc}")
                    logger.exception("Полная ошибка:")
                    continue
            
            # Дедупликация отзывов по тексту
            unique_reviews = []
            seen_texts = set()
            
            for review in page_reviews:
                review_text = review.review_text[:100] if review.review_text else ""
                if review_text not in seen_texts:
                    unique_reviews.append(review)
                    seen_texts.add(review_text)
            
            logger.info(f"После дедупликации: {len(unique_reviews)} уникальных отзывов")
            
            # Сохранение результатов страницы
            dataset.add_page_results(str(page.url), unique_reviews, len(chunks))
            dataset.save()
            
            all_reviews.extend(unique_reviews)
            logger.info(f"Страница {i} завершена. Всего собрано: {len(all_reviews)} отзывов")
            
        except Exception as exc:
            logger.error(f"Ошибка обработки страницы {page.url}: {exc}")
            continue

    # Финальная статистика
    stats = dataset.get_stats()
    logger.info(f"Извлечение завершено! Статистика: {stats}")

    return all_reviews

def get_dataset_stats(output_file: str = _OUTPUT_FILE) -> Dict[str, Any]:
    """Возвращает статистику датасета"""
    dataset = ReviewDataset(output_file)
    return dataset.get_stats()