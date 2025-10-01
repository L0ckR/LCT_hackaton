from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.schemas.parser import ParseRequest, ParseResponse
from app.services.review_parser import ParserError, extract_reviews

router = APIRouter(prefix="/parser", tags=["parser"])


@router.post("/reviews", response_model=ParseResponse)
async def parse_reviews_endpoint(
    payload: ParseRequest,
    user=Depends(get_current_user),
) -> ParseResponse:
    if not payload.pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must include at least one page",
        )

    try:
        reviews = await extract_reviews(payload.pages)
    except ParserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ParseResponse(reviews=reviews)
