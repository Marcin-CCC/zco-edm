"""
Chat router — proxy strumieniujący do n8n Chat Trigger + źródła odpowiedzi.

Przepływ:
1. Frontend wysyła POST /api/chat {message, session_id, request_id}.
2. Backend przekazuje do webhooka czatu n8n payload z chatInput, sessionId
   oraz requestId i sources_update_url (adres zwrotny do odłożenia źródeł).
3. Workflow n8n (nod Chunks Filter) zbiera chunki o score >= progu i przez
   HTTP Request wysyła POST na sources_update_url listę źródeł.
4. Backend zapamiętuje źródła (pamięć procesu, TTL) i wzbogaca je o file_id
   (dopasowanie po nazwie pliku w tabeli files) → frontend zrobi link
   do /api/files/{id}/download.
5. Frontend po zakończeniu strumienia odpytuje GET /api/chat/sources/{request_id}.
"""

import logging
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import User, File as FileModel, Conversation, Message
from app.schemas import (
    ChatRequest, ChatSourcesPayload,
    ConversationCreate, ConversationSummary, ConversationDetail, MessageOut, TurnCreate,
)
from app.settings.router import _load_cache_from_db, get_chat_webhook_url
from app.webhook_auth import verify_webhook_secret
from app.n8n_auth import outgoing_headers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Timeout: długi read (LLM może generować minutami), krótki connect
_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

# ==================== Magazyn źródeł (in-memory, TTL) ====================
# request_id -> {"sources": [...], "ts": epoch}
_sources_store: dict[str, dict] = {}
_SOURCES_TTL_SECONDS = 600  # 10 minut


def _purge_expired_sources() -> None:
    now = time.time()
    expired = [k for k, v in _sources_store.items() if now - v["ts"] > _SOURCES_TTL_SECONDS]
    for k in expired:
        _sources_store.pop(k, None)


def _enrich_with_file_ids(sources: list[dict], db: Session) -> list[dict]:
    """Dopasuj file_id po nazwie pliku (dla linku do pobrania)."""
    filenames = {s.get("filename") for s in sources if s.get("filename")}
    if not filenames:
        return sources
    rows = db.query(FileModel.id, FileModel.filename).filter(FileModel.filename.in_(filenames)).all()
    by_name = {filename: fid for fid, filename in rows}
    for s in sources:
        if not s.get("file_id") and s.get("filename") in by_name:
            s["file_id"] = by_name[s["filename"]]
    return sources


# ==================== Endpointy ====================
@router.post("")
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Wyślij wiadomość do czatu n8n i strumieniuj odpowiedź."""
    _load_cache_from_db(db)
    chat_url = get_chat_webhook_url()
    if not chat_url:
        raise HTTPException(
            status_code=503,
            detail="Adres webhooka czatu nie jest skonfigurowany (Ustawienia aplikacji).",
        )

    # Adres zwrotny dla źródeł — ten sam mechanizm co status_update_url plików
    from app.files.router import BACKEND_CALLBACK_URL
    request_id = payload.request_id or f"{current_user.id}-{int(time.time()*1000)}"

    n8n_body = {
        "action": "sendMessage",
        "sessionId": f"{current_user.id}:{payload.session_id}",
        "chatInput": payload.message,
        "requestId": request_id,
        "sources_update_url": f"{BACKEND_CALLBACK_URL}/api/chat/sources",
    }
    logger.info(f"[CHAT] user={current_user.username} session={payload.session_id} req={request_id} -> {chat_url}")

    client = httpx.AsyncClient(timeout=_TIMEOUT)

    try:
        req = client.build_request("POST", chat_url, json=n8n_body, headers=outgoing_headers())
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        logger.error(f"[CHAT] Błąd połączenia z n8n: {e}")
        raise HTTPException(status_code=502, detail=f"Nie można połączyć z czatem n8n: {e}")

    if upstream.status_code != 200:
        body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        detail = body.decode(errors="replace")[:500]
        logger.error(f"[CHAT] n8n zwrócił {upstream.status_code}: {detail}")
        raise HTTPException(status_code=502, detail=f"Czat n8n zwrócił {upstream.status_code}: {detail}")

    async def stream_body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        except httpx.HTTPError as e:
            logger.error(f"[CHAT] Przerwany strumień z n8n: {e}")
        finally:
            await upstream.aclose()
            await client.aclose()

    media_type = upstream.headers.get("content-type", "text/plain; charset=utf-8")
    return StreamingResponse(
        stream_body(),
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # wyłącz buforowanie w proxy
            "X-Chat-Request-Id": request_id,
        },
    )


@router.post("/sources", dependencies=[Depends(verify_webhook_secret)])
async def receive_sources(payload: ChatSourcesPayload, db: Session = Depends(get_db)):
    """Odbierz źródła odpowiedzi od n8n (auth: sekret webhooka, nie JWT).

    n8n wysyła: {"request_id": "...", "sources": [{"filename": "...", "page": 1, "score": 0.83}]}
    """
    _purge_expired_sources()
    sources = [s.model_dump(exclude_none=True) for s in payload.sources]
    sources = _enrich_with_file_ids(sources, db)
    _sources_store[payload.request_id] = {"sources": sources, "ts": time.time()}
    logger.info(f"[CHAT] Źródła dla req={payload.request_id}: {len(sources)} pozycji")
    return {"message": "Źródła zapisane", "request_id": payload.request_id, "count": len(sources)}


@router.get("/sources/{request_id}")
async def get_sources(
    request_id: str,
    current_user: User = Depends(get_current_user),
):
    """Pobierz źródła dla danego pytania (frontend, po zakończeniu strumienia)."""
    _purge_expired_sources()
    entry = _sources_store.get(request_id)
    return {"request_id": request_id, "sources": entry["sources"] if entry else []}


# ==================== Historia rozmów ====================
def _get_owned_conversation(conv_id: int, user: User, db: Session) -> Conversation:
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Rozmowa nie istnieje.")
    return conv


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista rozmów użytkownika (najnowsze pierwsze)."""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.post("/conversations", response_model=ConversationSummary, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Utwórz nową rozmowę. Tytuł = pierwsze pytanie (skrócone)."""
    title = (payload.title or "Nowa rozmowa").strip()[:200] or "Nowa rozmowa"
    conv = Conversation(user_id=current_user.id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pełny wątek rozmowy z wiadomościami."""
    conv = _get_owned_conversation(conv_id, current_user, db)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[MessageOut.model_validate(m) for m in conv.messages],
    )


@router.post("/conversations/{conv_id}/turn", status_code=201)
def append_turn(
    conv_id: int,
    payload: TurnCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zapisz jedną turę: pytanie użytkownika + odpowiedź asystenta."""
    conv = _get_owned_conversation(conv_id, current_user, db)
    db.add(Message(conversation_id=conv.id, role="user", content=payload.user_message))
    db.add(Message(
        conversation_id=conv.id, role="assistant",
        content=payload.assistant_message, sources=payload.sources or None,
    ))
    # dotknij updated_at (żeby rozmowa wskoczyła na górę listy)
    conv.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Tura zapisana", "conversation_id": conv.id}


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuń rozmowę wraz z wiadomościami."""
    conv = _get_owned_conversation(conv_id, current_user, db)
    db.delete(conv)
    db.commit()
    return {"message": "Rozmowa usunięta."}
