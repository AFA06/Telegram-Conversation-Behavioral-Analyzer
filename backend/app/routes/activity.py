from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.services import activity_analyzer
from app.services.statistics import messages_dataframe

router = APIRouter()

RoleParam = Query("both", pattern="^(me|other|both)$")


@router.get("/hourly")
def hourly(role: str = RoleParam, db: Session = Depends(get_current_db)) -> list[dict]:
    return activity_analyzer.hourly_activity(messages_dataframe(db), role)


@router.get("/weekday")
def weekday(role: str = RoleParam, db: Session = Depends(get_current_db)) -> list[dict]:
    return activity_analyzer.weekday_activity(messages_dataframe(db), role)


@router.get("/heatmap")
def heatmap(role: str = RoleParam, db: Session = Depends(get_current_db)) -> dict:
    return activity_analyzer.heatmap(messages_dataframe(db), role)


@router.get("/daily")
def daily(year: int = Query(...), month: int = Query(..., ge=1, le=12), db: Session = Depends(get_current_db)) -> list[dict]:
    return activity_analyzer.daily_activity(messages_dataframe(db), year, month)


@router.get("/available-months")
def available_months(db: Session = Depends(get_current_db)) -> list[dict]:
    df = messages_dataframe(db)
    if df.empty:
        return []
    pairs = df[["year", "month"]].drop_duplicates().sort_values(["year", "month"])
    return [{"year": int(r.year), "month": int(r.month)} for r in pairs.itertuples()]


@router.get("/top-windows")
def top_windows(
    role: str = RoleParam,
    window_minutes: int = Query(60, ge=15, le=360),
    top_n: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_current_db),
) -> list[dict]:
    return activity_analyzer.top_activity_windows(messages_dataframe(db), role, window_minutes, top_n)
