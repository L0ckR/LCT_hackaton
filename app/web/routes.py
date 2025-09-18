from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_user_from_token
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.review import Review
from app.models.user import User
from app.services.auth import authenticate_user

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="app/templates")


def _get_optional_user(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return get_user_from_token(token, db)
    except HTTPException:
        return None


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = _get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    recent_reviews = db.query(Review).order_by(Review.date.desc()).limit(20).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "reviews": recent_reviews},
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


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
            {"request": request, "error": "Invalid email or password."},
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
    return templates.TemplateResponse("register.html", {"request": request})


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
            {"request": request, "error": "Email already registered."},
            status_code=400,
        )
    user = User(email=email, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    response = RedirectResponse(url="/login?registered=1", status_code=303)
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
    imported = 0

    if file.filename.endswith(".json"):
        import json
        from datetime import datetime

        data = json.loads(contents)
        for item in data:
            review = Review(
                product=item.get("product"),
                text=item.get("text"),
                date=datetime.fromisoformat(item.get("date")) if item.get("date") else None,
            )
            db.add(review)
            imported += 1
        db.commit()
    elif file.filename.endswith(".csv"):
        import csv
        import io
        from datetime import datetime

        reader = csv.DictReader(io.StringIO(contents.decode()))
        for item in reader:
            review = Review(
                product=item.get("product"),
                text=item.get("text"),
                date=datetime.fromisoformat(item.get("date")) if item.get("date") else None,
            )
            db.add(review)
            imported += 1
        db.commit()
    else:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "reviews": db.query(Review).order_by(Review.date.desc()).limit(20).all(),
                "error": "Unsupported file type. Please upload JSON or CSV.",
            },
            status_code=400,
        )

    recent_reviews = db.query(Review).order_by(Review.date.desc()).limit(20).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "reviews": recent_reviews,
            "status": f"Imported {imported} reviews.",
        },
    )
