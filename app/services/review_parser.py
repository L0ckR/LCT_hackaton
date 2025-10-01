import json
import logging
import re
import textwrap
from typing import Iterable, List
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.parser import PagePayload, ParsedReview
from app.services.openai_client import create_chat_completion

logger = logging.getLogger(__name__)

_ALLOWED_SOURCES = [
    "sravni.ru",
    "sravni.ru/banki/gazprombank/otzyvy/", 
    "banki.ru",
    "banki.ros",
    "vbr.ru",
    "finsber",
    "vsezaimyonline.ru",
    "irecommend.ru",
    "2gis",
    "google maps",
    "yandex maps",
    "yandex zen",
    "apps.apple.com",
    "play.google.com",
    "vk.com",
    "telegram"
]

_SYSTEM_PROMPT = (
    "Ты эксперт по анализу отзывов о банковских продуктах. "
    "Тебе нужно аккуратно извлекать структурированные данные из неструктурированного текста. "
    "Отвечай строго в формате валидного JSON без пояснений и комментариев."
)

_RESPONSE_STRUCTURE_HINT = (
    '{"reviews": [ { "url": "...", "review_tag": "...", "date_review": "...", '
    '"user_name": "...", "user_city": "...", "review_title": "...", "review_text": "...", '
    '"review_status": "...", "rating": "строка", "bank_name": "...", "source": "..." } ]}'
)

_MAX_TEXT_LENGTH = 15000

class ParserError(Exception):
    """Raised when the review parser fails to extract data."""

def _clean_html(content: str) -> str:
    logger.debug(f"Начинаем очистку HTML контента длиной {len(content)} символов")
    
    soup = BeautifulSoup(content, "html.parser")
    
    for tag in soup([
        "script",
        "style",
        "head",
        "footer",
        "nav",
        "iframe",
        "noscript",
    ]):
        tag.decompose()
    
    for tag in soup.find_all(True):
        if tag.name != "img":
            tag.attrs = {}
        else:
            tag.attrs = {k: v for k, v in tag.attrs.items() if k == "alt"}
    
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"https?://\S+", "", text)
    
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH]
        logger.debug(f"Текст обрезан до {_MAX_TEXT_LENGTH} символов")
    
    logger.info(f"Очищенный текст длиной {len(text)} символов: {text[:500]}...")  # Логируем первые 500 символов
    return text

async def _fetch_content(url: str) -> str:
    logger.info(f"Загружаем контент с URL: {url}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        
        content = response.text
        logger.info(f"Получен контент длиной {len(content)} символов с {url}")
        return content

def _extract_json_block(payload: str) -> dict:
    if not payload:
        raise ParserError("Empty LLM response")
    
    logger.debug(f"Извлекаем JSON из ответа LLM: {payload[:200]}...")
    
    content = payload.strip()
    
    # Удаляем markdown блоки
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9]*", "", content)
        content = re.sub(r"```$", "", content).strip()
    
    # Пытаемся найти JSON объект в тексте
    json_patterns = [
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Простой JSON объект
        r'\{.*?"reviews".*?\}',  # JSON с полем reviews
        r'\{.*?\}',  # Любой JSON объект
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                # Очищаем найденный JSON от возможных артефактов
                cleaned_match = match.strip()
                
                # Удаляем возможные незавершенные строки в конце
                if cleaned_match.count('"') % 2 != 0:
                    # Если нечетное количество кавычек, пытаемся исправить
                    cleaned_match = re.sub(r'"[^"]*$', '"', cleaned_match)
                
                # Удаляем возможные незавершенные объекты в конце
                if cleaned_match.endswith(','):
                    cleaned_match = cleaned_match.rstrip(',')
                
                # Удаляем возможные незавершенные запятые
                cleaned_match = re.sub(r',\s*}', '}', cleaned_match)
                cleaned_match = re.sub(r',\s*]', ']', cleaned_match)
                
                result = json.loads(cleaned_match)
                if isinstance(result, dict) and 'reviews' in result:
                    logger.info(f"Успешно распарсен JSON с {len(result.get('reviews', []))} отзывами")
                    return result
            except json.JSONDecodeError as e:
                logger.debug(f"Не удалось распарсить JSON: {e}, попробуем следующий паттерн")
                continue
    
    # Если ничего не сработало, пытаемся исправить JSON вручную
    try:
        # Ищем начало и конец JSON объекта
        start_idx = content.find('{')
        if start_idx == -1:
            raise ParserError("LLM response does not contain JSON")
        
        # Находим соответствующий закрывающий символ
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
        
        # Исправляем возможные проблемы
        json_str = re.sub(r',\s*}', '}', json_str)  # Убираем лишние запятые
        json_str = re.sub(r',\s*]', ']', json_str)
        
        result = json.loads(json_str)
        logger.info(f"JSON исправлен и распарсен с {len(result.get('reviews', []))} отзывами")
        return result
        
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Не удалось распарсить JSON после всех попыток: {e}")
        logger.error(f"Проблемный контент: {content[:500]}...")
        raise ParserError(f"LLM response does not contain valid JSON: {e}")

def _default_source(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    host = host.lstrip("www.")
    return host or None

def _extract_reviews_simple(html: str, url: str) -> List[ParsedReview]:
    """Простое извлечение отзывов без LLM для тестирования"""
    logger.info("Используем простое извлечение отзывов без LLM")
    
    soup = BeautifulSoup(html, "html.parser")
    reviews = []
    
    # Ищем различные селекторы для отзывов
    review_selectors = [
        '.review', '.reviews .review', '.review-item', '.comment',
        '[class*="review"]', '[class*="comment"]', '[class*="feedback"]',
        '.user-review', '.bank-review', '.otzyv'
    ]
    
    found_reviews = []
    for selector in review_selectors:
        elements = soup.select(selector)
        if elements:
            logger.info(f"Найдено {len(elements)} элементов с селектором: {selector}")
            found_reviews.extend(elements)
    
    # Если не нашли по селекторам, ищем по тексту
    if not found_reviews:
        logger.info("Не найдено элементов по селекторам, ищем по тексту")
        # Ищем блоки с текстом, содержащим ключевые слова
        text_elements = soup.find_all(text=lambda text: text and any(word in text.lower() for word in ['отзыв', 'рейтинг', 'звезд', 'пользователь']))
        for text_elem in text_elements:
            parent = text_elem.parent
            if parent and parent not in found_reviews:
                found_reviews.append(parent)
    
    logger.info(f"Всего найдено {len(found_reviews)} потенциальных отзывов")
    
    # Создаем отзывы из найденных элементов
    for i, element in enumerate(found_reviews[:10]):  # Ограничиваем 10 отзывами
        try:
            # Извлекаем текст
            text = element.get_text(strip=True)
            if len(text) < 20:  # Пропускаем слишком короткие тексты
                continue
                
            # Создаем базовый отзыв
            review_data = {
                "url": url,
                "review_tag": f"simple_{i+1}",
                "date_review": None,
                "user_name": None,
                "user_city": None,
                "review_title": f"Отзыв {i+1}",
                "review_text": text[:500] + "..." if len(text) > 500 else text,
                "review_status": "unknown",
                "rating": None,
                "bank_name": _default_source(url),
                "source": _default_source(url)
            }
            
            # Пытаемся найти рейтинг
            rating_elem = element.find(class_=lambda x: x and 'rating' in x.lower()) or element.find(class_=lambda x: x and 'star' in x.lower())
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                # Извлекаем цифры из рейтинга
                import re
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    review_data["rating"] = rating_match.group(1)
            
            # Пытаемся найти имя пользователя
            name_elem = element.find(class_=lambda x: x and any(word in x.lower() for word in ['name', 'user', 'author']))
            if name_elem:
                review_data["user_name"] = name_elem.get_text(strip=True)
            
            # Пытаемся найти дату
            date_elem = element.find(class_=lambda x: x and any(word in x.lower() for word in ['date', 'time', 'created']))
            if date_elem:
                review_data["date_review"] = date_elem.get_text(strip=True)
            
            # Валидируем и добавляем отзыв
            review = ParsedReview.model_validate(review_data)
            reviews.append(review)
            logger.info(f"Создан простой отзыв {i+1}: {text[:100]}...")
            
        except Exception as e:
            logger.warning(f"Ошибка при создании простого отзыва {i+1}: {e}")
            continue
    
    logger.info(f"Создано {len(reviews)} простых отзывов")
    
    # Выводим детали созданных отзывов
    for i, review in enumerate(reviews, 1):
        logger.info(f"Простой отзыв {i}: {review.review_text[:100]}...")
        logger.info(f"  - Рейтинг: {review.rating}")
        logger.info(f"  - Пользователь: {review.user_name}")
        logger.info(f"  - Дата: {review.date_review}")
    
    return reviews

def _sources_hint() -> str:
    return "\n".join(f"- {source}" for source in _ALLOWED_SOURCES)

async def _run_llm(url: str, text: str) -> dict:
    if not settings.FOUNDATION_API_KEY:
        raise ParserError("FOUNDATION_API_KEY is not configured")
    
    logger.info(f"Отправляем запрос в LLM для URL: {url}")
    logger.debug(f"Текст для анализа (первые 300 символов): {text[:300]}...")
    
    trimmed_text = text[:_MAX_TEXT_LENGTH]
    
    prompt_template = textwrap.dedent(
        '''
        Тебе передан очищенный текст страницы с отзывами о банковских продуктах. URL страницы: {url}.
        Источник относится к одному из следующих агрегаторов и платформ:
        {sources}
        
        ВАЖНО: Ищи отзывы пользователей о банковских услугах, кредитах, депозитах, картах и т.д.
        Отзывы могут содержать:
        - Имена пользователей
        - Даты отзывов
        - Рейтинги (звезды, цифры)
        - Текст отзыва
        - Название банка
        - Город пользователя
        - Статус отзыва (положительный/отрицательный)
        
        Проанализируй текст и извлеки как можно больше отдельных отзывов.
        Для каждого отзыва собери поля: url, review_tag, date_review, user_name, user_city,
        review_title, review_text, review_status, rating, bank_name, source.
        
        ПРАВИЛА: 
        - Все поля должны быть строками, включая rating (например: "5", "4.5", "1")
        - Если каких-то данных нет в тексте, ставь null
        - Не придумывай данных, которых нет в тексте
        - Ищи реальные отзывы пользователей, а не рекламные тексты
        
        Отвечай строго JSON объектом следующей структуры: {structure}.
        url каждого отзыва по умолчанию равен адресу страницы, если не указано иное.
        Максимум 20 отзывов.
        
        Текст страницы для анализа:
        """{text}"""
        '''
    ).strip()
    
    user_prompt = prompt_template.format(
        url=url,
        sources=_sources_hint(),
        structure=_RESPONSE_STRUCTURE_HINT,
        text=trimmed_text,
    )
    
    logger.debug(f"Промпт для LLM (первые 500 символов): {user_prompt[:500]}...")
    logger.debug(f"Полная длина промпта: {len(user_prompt)} символов")
    
    try:
        completion = await create_chat_completion(
            model=settings.FOUNDATION_CHAT_MODEL,
            temperature=0.0,
            top_p=0.9,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        
        logger.info("Получен ответ от LLM")
        
    except (APIConnectionError, APITimeoutError, APIStatusError, RateLimitError) as exc:
        logger.warning("LLM request failed: %s", exc)
        raise ParserError("LLM request failed") from exc
    except Exception as exc:
        logger.exception("Unexpected error during LLM call")
        raise ParserError("Unexpected LLM error") from exc
    
    message = completion.choices[0].message.content if completion.choices else ""
    logger.info(f"Получен ответ от LLM длиной {len(message)} символов")
    logger.debug(f"Сырой ответ от LLM: {message}")
    
    if not message:
        raise ParserError("LLM returned empty response")
    
    data = _extract_json_block(message)
    
    if not isinstance(data, dict):
        raise ParserError("LLM returned non-object payload")
    
    logger.info(f"Обработанный ответ LLM: {json.dumps(data, ensure_ascii=False, indent=2)}")
    return data

def _coerce_reviews(raw: dict, page: PagePayload) -> List[ParsedReview]:
    logger.info(f"Валидируем отзывы для страницы: {page.url}")
    logger.debug(f"Сырые данные от LLM: {json.dumps(raw, ensure_ascii=False, indent=2)}")
    
    items = raw.get("reviews") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        logger.warning(f"Поле reviews не является списком: {type(items)}, значение: {items}")
        return []
    
    logger.info(f"Найдено {len(items)} потенциальных отзывов")
    
    reviews: List[ParsedReview] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            logger.warning(f"Skipping non-dict review item at position {index}: {type(item)} - {item}")
            continue
        
        payload = dict(item)
        # Убеждаемся, что URL валидный
        if "url" not in payload or not payload["url"]:
            payload["url"] = str(page.url)
        payload.setdefault("source", _default_source(str(page.url)))
        
        # Преобразуем типы данных для совместимости со схемой
        if "rating" in payload and payload["rating"] is not None:
            payload["rating"] = str(payload["rating"])
        
        if "date_review" in payload and payload["date_review"] is not None:
            payload["date_review"] = str(payload["date_review"])
            
        # Конвертируем другие поля в строки если нужно
        string_fields = ["review_tag", "user_name", "user_city", "review_title", 
                        "review_text", "review_status", "bank_name"]
        for field in string_fields:
            if field in payload and payload[field] is not None:
                payload[field] = str(payload[field])
        
        logger.debug(f"Валидируем отзыв #{index}: {json.dumps(payload, ensure_ascii=False)}")
        
        # Проверяем валидность URL
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(payload.get("url", ""))
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.warning(f"Invalid URL for review #{index}: {payload.get('url', 'None')}")
                payload["url"] = str(page.url)  # Используем URL страницы как fallback
        except Exception as e:
            logger.warning(f"URL validation error for review #{index}: {e}")
            payload["url"] = str(page.url)
        
        try:
            review = ParsedReview.model_validate(payload)
            reviews.append(review)
            logger.debug(f"Отзыв #{index} успешно валидирован")
        except ValidationError as exc:
            logger.warning("Validation failed for review #%s on %s: %s", index, page.url, exc)
            logger.warning(f"Проблемные данные: {payload}")
            continue
    
    logger.info(f"Успешно валидировано {len(reviews)} отзывов из {len(items)}")
    if len(reviews) == 0 and len(items) > 0:
        logger.warning(f"Все {len(items)} отзывов не прошли валидацию!")
    return reviews

async def extract_reviews(pages: Iterable[PagePayload]) -> List[ParsedReview]:
    logger.info("Начинаем извлечение отзывов")
    
    pages_list = list(pages)
    logger.info(f"Получено {len(pages_list)} страниц для обработки")
    
    for i, page in enumerate(pages_list, 1):
        logger.info(f"Страница {i}: {page.url}")
        if page.content:
            logger.info(f"  - Предоставлен контент длиной {len(page.content)} символов")
        else:
            logger.info(f"  - Контент будет загружен по URL")
    
    collected: List[ParsedReview] = []
    
    for i, page in enumerate(pages_list, 1):
        logger.info(f"Обрабатываем страницу {i}/{len(pages_list)}: {page.url}")
        
        try:
            if page.content and len(page.content.strip()) > 100:
                logger.info(f"Используем предоставленный контент для {page.url}")
                html = page.content
            else:
                logger.info(f"Загружаем контент для {page.url}")
                html = await _fetch_content(str(page.url))
        except Exception as exc:
            logger.warning("Failed to load page %s: %s", page.url, exc)
            continue
        
        cleaned = _clean_html(html)
        if not cleaned or len(cleaned.strip()) < 100:
            logger.warning(f"Empty or too short cleaned content for %s (length: {len(cleaned) if cleaned else 0})", page.url)
            continue
        
        logger.info(f"Очищенный контент для анализа (первые 1000 символов): {cleaned[:1000]}...")
        
        review_indicators = ['отзыв', 'рейтинг', 'звезд', 'пользователь', 'клиент', 'оценка', 'review', 'rating']
        has_review_content = any(indicator.lower() in cleaned.lower() for indicator in review_indicators)
        
        if not has_review_content:
            logger.warning(f"Страница {page.url} не содержит признаков отзывов. Пропускаем.")
            continue
        
        logger.info(f"Найдены признаки отзывов на странице {page.url}")
        
        use_simple_parsing = True  
        
        if use_simple_parsing:
            logger.info(f"Используем простое извлечение отзывов для {page.url}")
            reviews = _extract_reviews_simple(html, str(page.url))
        else:
            try:
                logger.info(f"Отправляем запрос в LLM для страницы {page.url}")
                llm_payload = await _run_llm(str(page.url), cleaned)
                logger.info(f"Получен ответ от LLM для страницы {page.url}")
            except ParserError as exc:
                logger.error(f"LLM parsing failed for %s: %s", page.url, exc)
                continue
            except Exception as exc:
                logger.error(f"Unexpected error during LLM processing for %s: %s", page.url, exc)
                continue
            
            reviews = _coerce_reviews(llm_payload, page)
        
        if not reviews:
            logger.warning("No reviews extracted for %s", page.url)
            if not use_simple_parsing:
                logger.warning(f"LLM payload was: {json.dumps(llm_payload, ensure_ascii=False, indent=2)}")
            
            if 'отзыв' in cleaned.lower() or 'review' in cleaned.lower():
                logger.info("Пытаемся создать общий отзыв из контента страницы")
                fallback_review = {
                    "url": str(page.url),
                    "review_tag": "general",
                    "date_review": None,
                    "user_name": None,
                    "user_city": None,
                    "review_title": f"Отзывы о {_default_source(str(page.url))}",
                    "review_text": cleaned[:500] + "..." if len(cleaned) > 500 else cleaned,
                    "review_status": "mixed",
                    "rating": None,
                    "bank_name": _default_source(str(page.url)),
                    "source": _default_source(str(page.url))
                }
                
                try:
                    review = ParsedReview.model_validate(fallback_review)
                    reviews = [review]
                    logger.info("Создан fallback отзыв из контента страницы")
                except Exception as e:
                    logger.warning(f"Не удалось создать fallback отзыв: {e}")
            
            if not reviews:
                continue
        
        collected.extend(reviews)
        logger.info(f"Добавлено {len(reviews)} отзывов с {page.url}. Всего собрано: {len(collected)}")
    
    logger.info(f"Завершено извлечение отзывов. Итого собрано: {len(collected)} отзывов")
    return collected