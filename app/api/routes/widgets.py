from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.widget import Widget
from app.schemas.widget import WidgetCreate, WidgetOut
from app.services.widgets import (
    METRIC_MAP,
    compute_widget_value,
    timeseries_for_metric,
)

router = APIRouter(prefix="/dashboard/widgets", tags=["widgets"])


@router.get("/", response_model=List[WidgetOut])
def list_widgets(
    db: Session = Depends(get_db), user=Depends(get_current_user)
):
    widgets = (
        db.query(Widget)
        .filter(Widget.owner_id == user.id)
        .order_by(Widget.id.asc())
        .all()
    )

    response: List[WidgetOut] = []
    for widget in widgets:
        value = compute_widget_value(widget, db)
        response.append(
            WidgetOut(
                id=widget.id,
                title=widget.title,
                metric=widget.metric,
                value=value,
                visualization=widget.visualization,
            )
        )
    return response


@router.post("/", response_model=WidgetOut, status_code=status.HTTP_201_CREATED)
def create_widget(
    payload: WidgetCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if payload.metric not in METRIC_MAP:
        raise HTTPException(status_code=400, detail="Unsupported metric")
    widget = Widget(
        title=payload.title,
        metric=payload.metric,
        visualization=payload.visualization,
        owner_id=user.id,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    value = compute_widget_value(widget, db)
    return WidgetOut(
        id=widget.id,
        title=widget.title,
        metric=widget.metric,
        value=value,
        visualization=widget.visualization,
    )


@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(
    widget_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    widget = (
        db.query(Widget)
        .filter(Widget.id == widget_id, Widget.owner_id == user.id)
        .first()
    )
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    db.delete(widget)
    db.commit()
    return None


@router.get("/{widget_id}/timeseries")
def widget_timeseries(
    widget_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    widget = (
        db.query(Widget)
        .filter(Widget.id == widget_id, Widget.owner_id == user.id)
        .first()
    )
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    if widget.metric not in METRIC_MAP:
        raise HTTPException(status_code=400, detail="Unsupported metric")
    data = timeseries_for_metric(db, widget.metric) if widget.visualization != "metric" else []
    return {"metric": widget.metric, "visualization": widget.visualization, "data": data}
