import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.dependencies import get_current_user
from app.schemas.parser import ParseJobRequest, ParseJobResult, ParserSource
from app.services.review_parser import ParserService, ParserServiceError

router = APIRouter(prefix="/parser", tags=["parser"])

logger = logging.getLogger(__name__)
parser_service = ParserService()


@router.post("/run", response_model=ParseJobResult)
async def run_parser_job(job: ParseJobRequest, user=Depends(get_current_user)):
    try:
        result = await parser_service.parse_gazprombank_reviews(
            page_size=job.page_size,
            max_pages=job.max_pages,
            start_date=job.start_date,
            output_filename=job.output_filename,
            finger_print=job.finger_print,
            delay_range=(job.min_delay, job.max_delay),
        )
    except ParserServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc: 
        logger.exception("Unexpected parser failure: %s", exc)
        raise HTTPException(status_code=500, detail="Parser job failed") from exc

    download_path = router.url_path_for(
        "download_parser_file",
        filename=result.filename,
    )
    return ParseJobResult(
        source=ParserSource(result.source),
        filename=result.filename,
        csv_path=str(result.csv_path),
        download_url=str(download_path),
        rows_written=result.rows_written,
        metadata=result.metadata,
        rows=result.rows,
    )


@router.get(
    "/files/{filename}",
    response_class=FileResponse,
    name="download_parser_file",
)
async def download_parser_file(filename: str, user=Depends(get_current_user)):
    try:
        path = parser_service.resolve_csv_path(filename)
    except ParserServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="text/csv",
        filename=path.name,
    )
