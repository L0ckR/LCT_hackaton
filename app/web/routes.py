from typing import Dict, Optional
from urllib.parse import quote_plus

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_user_from_token
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal
from app.models.review import Review
from app.models.user import User
from app.models.widget import Widget
from app.realtime import broadcast_refresh, dashboard_events
from app.schemas.widget import MetricType, VisualizationType
from app.services.auth import authenticate_user
from app.services.widgets import METRIC_MAP, compute_widget_value, timeseries_for_metric
from app.tasks.import_reviews import import_reviews_task

router = APIRouter(tags=["web"])
ws_router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


AVAILABLE_METRICS: Dict[MetricType, str] = {
    key: definition.label for key, definition in METRIC_MAP.items()
}

AVAILABLE_VISUALIZATIONS: Dict[VisualizationType, str] = {
    "metric": "Single value",
    "line": "Line chart",
    "bar": "Bar chart",
}


def _get_optional_user(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return get_user_from_token(token, db)
    except HTTPException:
        return None


def _dashboard_context(
    request: Request,
    db: Session,
    user: User,
    *,
    status: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict:
    recent_reviews = db.query(Review).order_by(Review.date.desc()).limit(20).all()
    widgets = (
        db.query(Widget)
        .filter(Widget.owner_id == user.id)
        .order_by(Widget.id.asc())
        .all()
    )
    widget_cards = [
        {
            "id": widget.id,
            "title": widget.title,
            "metric": widget.metric,
            "label": AVAILABLE_METRICS.get(widget.metric, widget.metric),
            "value": compute_widget_value(widget, db),
            "visualization": widget.visualization,
        }
        for widget in widgets
    ]

    total_reviews = db.query(Review).count()
    avg_sentiment = db.query(func.avg(Review.sentiment_score)).scalar() or 0
    latest_insights = (
        db.query(Review)
        .filter(Review.insights.isnot(None))
        .order_by(Review.date.desc())
        .limit(5)
        .all()
    )
    highlights: list[str] = []
    for review in latest_insights:
        details = review.insights or {}
        if isinstance(details, dict):
            highlights.extend(details.get("highlights", [])[:2])

    auth_token = request.cookies.get("access_token", "")

    return {
        "request": request,
        "user": user,
        "reviews": recent_reviews,
        "widgets": widget_cards,
        "available_metrics": AVAILABLE_METRICS,
        "available_visualizations": AVAILABLE_VISUALIZATIONS,
        "overview": {
            "total_reviews": total_reviews,
            "average_sentiment": round(float(avg_sentiment), 2) if avg_sentiment else 0,
            "highlights": highlights,
        },
        "status": status,
        "error": error,
        "auth_token": auth_token,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = _get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    status = request.query_params.get("status")
    error = request.query_params.get("error")
    context = _dashboard_context(request, db, user, status=status, error=error)
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    status = request.query_params.get("status")
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": None, "status": status, "error": error},
    )


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "Invalid email or password.",
            },
            status_code=400,
        )
    token = create_access_token({"sub": user.email})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        "access_token",
        token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "error": "Email already registered.",
            },
            status_code=400,
        )
    user = User(email=email, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    response = RedirectResponse(
        url=f"/login?status={quote_plus('Account created. Please sign in.')}",
        status_code=303,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.post("/upload")
async def upload_reviews(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = _get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    contents = await file.read()
    records = []

    if file.filename.endswith(".json"):
        import json

        data = json.loads(contents)
        if isinstance(data, dict):
            data = [data]
        records = list(data)
    elif file.filename.endswith(".csv"):
        import csv
        import io

        reader = csv.DictReader(io.StringIO(contents.decode()))
        records = list(reader)
    else:
        error_message = quote_plus("Unsupported file type. Please upload JSON or CSV.")
        return RedirectResponse(url=f"/?error={error_message}", status_code=303)

    job = import_reviews_task.delay(records)
    status_message = quote_plus("Import started…")
    return RedirectResponse(
        url=f"/?status={status_message}&job={job.id}",
        status_code=303,
    )


@router.post("/widgets")
def add_widget(
    request: Request,
    title: str = Form(...),
    metric: MetricType = Form(...),
    visualization: VisualizationType = Form("metric"),
    db: Session = Depends(get_db),
):
    user = _get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if metric not in AVAILABLE_METRICS:
        return RedirectResponse(
            url=f"/?error={quote_plus('Unsupported metric selection.')}",
            status_code=303,
        )

    if visualization not in AVAILABLE_VISUALIZATIONS:
        return RedirectResponse(
            url=f"/?error={quote_plus('Unsupported visualization type.')}",
            status_code=303,
        )

    widget = Widget(title=title, metric=metric, visualization=visualization, owner_id=user.id)
    db.add(widget)
    db.commit()

    return RedirectResponse(url=f"/?status={quote_plus('Widget added.')}", status_code=303)


@router.post("/widgets/{widget_id}/delete")
def delete_widget(
    widget_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    widget = (
        db.query(Widget)
        .filter(Widget.id == widget_id, Widget.owner_id == user.id)
        .first()
    )
    if widget:
        db.delete(widget)
        db.commit()
        return RedirectResponse(
            url=f"/?status={quote_plus('Widget removed.')}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/?error={quote_plus('Widget not found.')}",
        status_code=303,
    )


@router.get("/widgets/{widget_id}/timeseries")
def widget_timeseries(
    widget_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_optional_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    widget = (
        db.query(Widget)
        .filter(Widget.id == widget_id, Widget.owner_id == user.id)
        .first()
    )
    if not widget:
        return JSONResponse(status_code=404, content={"detail": "Widget not found"})

    try:
        data = (
            timeseries_for_metric(db, widget.metric)
            if widget.visualization != "metric"
            else []
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return JSONResponse(
        content={
            "metric": widget.metric,
            "visualization": widget.visualization,
            "data": data,
        }
    )


@ws_router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    db = SessionLocal()
    try:
        token = websocket.cookies.get("access_token")
        if not token:
            auth_header = websocket.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
        if not token:
            await websocket.close(code=1008)
            return
        try:
            get_user_from_token(token, db)
        except HTTPException:
            await websocket.close(code=1008)
            return

        await dashboard_events.connect(websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await dashboard_events.disconnect(websocket)
    except Exception:
        await dashboard_events.disconnect(websocket)
        await websocket.close(code=1011)
    finally:
        db.close()
