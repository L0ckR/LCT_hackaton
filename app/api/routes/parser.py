import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.schemas.parser import ParseRequest, ParseResponse
from app.services.review_parser import ParserError, extract_reviews

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parser", tags=["parser"])

@router.post("/reviews", response_model=ParseResponse)
async def parse_reviews_endpoint(
    payload: ParseRequest,
    user=Depends(get_current_user),
) -> ParseResponse:

    logger.info(f"Количество страниц: {len(payload.pages)}")
    
    if not payload.pages:
        logger.warning("Запрос не содержит страниц")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must include at least one page",
        )

    try:
        logger.info("Вызываем функцию extract_reviews")
        reviews = await extract_reviews(payload.pages)
        logger.info(f"Парсинг завершен. Найдено {len(reviews)} отзывов")
    except ParserError as exc:
        logger.error(f"Ошибка парсера: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Неожиданная ошибка: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    logger.info(f"Возвращаем {len(reviews)} отзывов пользователю")
    return ParseResponse(reviews=reviews)
