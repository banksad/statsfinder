from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path as FilePath
from pydantic import BaseModel

from app.services.chat import ask_chat, build_chat_retrieval_bundle
from app.services.postgres import list_datasets

BASE_DIR = FilePath(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    dataset_id: str | None = None


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    """
    Experimental source-grounded chat page.
    """
    datasets = list_datasets()

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "datasets": datasets,
            "active_nav": "chat",
        },
    )


@router.post("/v1/chat/retrieve")
def chat_retrieve_endpoint(
    request_body: ChatRequest,
) -> dict[str, Any]:
    """
    Retrieve SDMX series and reference chunks for a chat question.

    This endpoint is useful for debugging the grounding before generation.
    """
    question = request_body.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question must not be empty.",
        )

    try:
        return build_chat_retrieval_bundle(
            question=question,
            dataset_id=request_body.dataset_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Chat retrieval is not available: {exc}",
        ) from exc


@router.post("/v1/chat/ask")
def chat_ask_endpoint(
    request_body: ChatRequest,
) -> dict[str, Any]:
    """
    Retrieve source-backed context and generate a short grounded answer.
    """
    question = request_body.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question must not be empty.",
        )

    try:
        return ask_chat(
            question=question,
            dataset_id=request_body.dataset_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Chat is not available: {exc}",
        ) from exc
