from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.schemas import AskIn
from app.services import ask_engine

router = APIRouter()


@router.post("/ask")
def ask(payload: AskIn, db: Session = Depends(get_current_db)) -> dict:
    """Section 33: natural-language questions, answered locally by matching
    keywords to the already-computed statistics — no LLM, no raw messages
    involved unless the user explicitly wires up an external one later.
    """
    return ask_engine.answer(db, payload.question)
