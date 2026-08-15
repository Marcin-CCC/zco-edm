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
import re
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import (
    Conversation, File as FileModel, Message, OcenaOdpowiedzi, User,
)
from app.schemas import (
    ChatRequest, ChatSourcesPayload, OcenaCreate,
    ConversationCreate, ConversationSummary, ConversationDetail, MessageOut, TurnCreate,
)
from app.version import get_version
from app.chat.definicje import pytanie_definicyjne
from app.chat.formulka import bez_koncowej_formulki, filtruj_strumien
from app.settings.router import _load_cache_from_db, get_chat_webhook_url
from app.webhook_auth import verify_webhook_secret
from app.n8n_auth import outgoing_headers
from app.rbac import readable_folder_ids
from app.activity import chat_started, chat_finished, is_chat_active
from app.config import settings

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
    przeterminowane = [k for k, v in _diagnostyka_store.items()
                       if now - v["ts"] > _SOURCES_TTL_SECONDS]
    for k in przeterminowane:
        _diagnostyka_store.pop(k, None)


# request_id -> migawka planu wyszukiwania. Odkładamy ją w chwili zadania pytania,
# żeby ocena wystawiona przez użytkownika niosła kontekst: którą ścieżką poszło
# wyszukiwanie i co trafiło do modelu. Bez tego zgłoszenie „zła odpowiedź" jest
# nieanalizowalne kilka dni później, bo indeks w międzyczasie się zmienia.
_diagnostyka_store: dict[str, dict] = {}


# Odpowiedzi, których NIE przenosimy do historii rozmowy (zatruwają kolejne tury:
# model widzi własną odmowę i powiela ją mimo dobrego kontekstu).
_NO_ANSWER = "Niestety, nie znaleziono w dokumentach informacji na ten temat."
# Tury, które NIE niosą odpowiedzi — nie wolno ich wpuścić do historii dla modelu
# (odmowa w pamięci powoduje kolejne odmowy, zob. 0.5.4). Porównujemy po zdjęciu
# ewentualnego podkreślnika kursywy, bo te komunikaty występowały w obu postaciach.
_NO_MATCH_PREFIX = "_Nie znalazłem dokumentów spełniających kryteria"
_BEZ_ODPOWIEDZI_PREFIKSY = (
    "Nie znalazłem dokumentów spełniających kryteria",
    "Nie wiem, o które dokumenty chodzi",
    "W systemie nie ma rodzaju dokumentów",
)

_HISTORY_TURNS = 3          # ile ostatnich par pytanie–odpowiedź
_HISTORY_USER_CHARS = 300   # przycięcie pytania
_HISTORY_ASSIST_CHARS = 700  # przycięcie odpowiedzi


# Inline znaczniki cytowań („[Źródło 3]", „[Źródło 2, 5]") — zapisujemy je w treści
# odpowiedzi (frontend robi z nich klikalne odnośniki), ale do historii dla modelu
# przekazujemy tekst bez nich, żeby nie zaśmiecać promptu.
_MARKER_RE = re.compile(r"\s*\[{1,2}\s*Źród(?:ło|ła)\s*\d+(?:\s*,\s*\d+)*\s*\]{1,2}", re.IGNORECASE)


def _strip_markers(content: str) -> str:
    return _MARKER_RE.sub("", content or "")


# Adnotacja kursywą, którą frontend dokleja NAD odpowiedzią modelu („_Poniżej odpowiedź
# na podstawie treści dokumentów:_"). Nie jest odpowiedzią — przy rozpoznawaniu odmowy
# trzeba ją zdjąć, inaczej tura „adnotacja + nie znaleziono" wygląda jak zwykła
# odpowiedź i trafia do historii, choć nie niesie żadnej treści.
_ADNOTACJA_RE = re.compile(r"^\s*_[^\n]*_\s*\n+")


def _is_refusal(content: str) -> bool:
    c = (content or "").replace(" ", " ").strip()
    if c.rstrip() == _NO_ANSWER or c.startswith(_NO_MATCH_PREFIX):
        return True
    bez_kursywy = c.lstrip("_")
    if bez_kursywy.startswith(_BEZ_ODPOWIEDZI_PREFIKSY):
        return True
    return _ADNOTACJA_RE.sub("", c, count=1).strip() == _NO_ANSWER


def build_history(db: Session, user: User, session_id: str) -> str:
    """Zbuduj historię rozmowy dla n8n — BEZ odmów.

    Zastępuje węzeł Simple Memory, który zapisywał wszystko automatycznie: gdy raz
    padła odmowa („nie znaleziono"), model widział ją w pamięci i powtarzał dla
    kolejnych podobnych pytań, nawet mając dobry kontekst. Tutaj pomijamy całe tury
    zakończone odmową, a resztę przycinamy do budżetu kontekstu.

    Zwraca tekst „Użytkownik: … / Asystent: …" albo pusty string.
    """
    try:
        conv_id = int(str(session_id).strip())
    except (TypeError, ValueError):
        return ""

    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv or conv.user_id != user.id:
        return ""

    # Sparuj kolejne wiadomości user→assistant i odrzuć tury z odmową
    turns: list[tuple[str, str]] = []
    pending_user: str | None = None
    for m in conv.messages:
        if m.role == "user":
            pending_user = m.content or ""
        elif m.role == "assistant" and pending_user is not None:
            if not _is_refusal(m.content):
                turns.append((pending_user, m.content or ""))
            pending_user = None

    if not turns:
        return ""

    lines = []
    for u, a in turns[-_HISTORY_TURNS:]:
        # Rozmowy sprzed poprawki mają formułkę doklejoną na końcu odpowiedzi. Wzorzec
        # podany modelowi w historii sam zachęca do powtórki, więc go stąd zdejmujemy.
        odpowiedz = bez_koncowej_formulki(_strip_markers(a))
        lines.append(f"Użytkownik: {u.strip()[:_HISTORY_USER_CHARS]}")
        lines.append(f"Asystent: {odpowiedz.strip()[:_HISTORY_ASSIST_CHARS]}")
    return "\n".join(lines)


def _enrich_with_file_ids(sources: list[dict], db: Session) -> list[dict]:
    """Dołóż do źródeł identyfikator pliku, typ dokumentu i kluczowe pola.

    Faza B (#7): źródła pokazują rozpoznany typ i numer/datę, więc zamiast samej
    nazwy pliku użytkownik widzi np. „Zarządzenie nr 8/2023".

    IDENTYFIKACJA PO `file_id`, NIE PO NAZWIE. Nazwa pliku nie jest unikalna:
    zmierzone na bazie ZCO (2026-08-10) — 9 nazw powtarza się, obejmując 18
    dokumentów. Dwa różne zarządzenia leżą pod nazwą „1.pdf" (1/2009 i 1/2010).
    Dopasowanie po nazwie sklejało je w jedno: odpowiedź pochodziła ze strony 4
    dokumentu 1/2010, a etykieta i odnośnik prowadziły do 1/2009 — dokumentu,
    który ma jedną stronę. Klikając cytowanie, użytkownik pobierał NIE TEN plik.

    Nazwy używamy więc tylko awaryjnie i tylko wtedy, gdy wskazuje dokładnie jeden
    dokument. Przy nazwie niejednoznacznej zostawiamy źródło bez `file_id`: lepiej
    pokazać samą nazwę bez odnośnika niż odesłać do niewłaściwego dokumentu.
    """
    from collections import Counter

    # 1) Droga pewna: n8n przysłał `file_id` (payload Qdranta go niesie).
    po_id: dict[int, tuple[int, dict]] = {}
    identyfikatory = {s["file_id"] for s in sources if s.get("file_id")}
    if identyfikatory:
        for fid, _fn, meta in (
            db.query(FileModel.id, FileModel.filename, FileModel.metadata_)
            .filter(FileModel.id.in_(identyfikatory)).all()
        ):
            po_id[fid] = (fid, meta)

    # 2) Droga awaryjna: po nazwie, ale WYŁĄCZNIE gdy jest jednoznaczna.
    by_name: dict[str, tuple[int, dict]] = {}
    filenames = {s.get("filename") for s in sources
                 if s.get("filename") and not s.get("file_id")}
    if filenames:
        rows = (
            db.query(FileModel.id, FileModel.filename, FileModel.metadata_)
            .filter(FileModel.filename.in_(filenames))
            .all()
        )
        ile_o_nazwie = Counter(filename for _fid, filename, _meta in rows)
        by_name = {filename: (fid, meta) for fid, filename, meta in rows
                   if ile_o_nazwie[filename] == 1}
        niejednoznaczne = sorted(n for n, ile in ile_o_nazwie.items() if ile > 1)
        if niejednoznaczne:
            logger.warning(
                f"[CHAT] Nazwa pliku nie wskazuje jednego dokumentu: {niejednoznaczne} — "
                f"źródła zostają bez odnośnika. Trwałe rozwiązanie: n8n ma przysyłać "
                f"file_id w źródłach (zob. docs/n8n-zrodla-file-id.md)."
            )
    if not po_id and not by_name:
        return sources

    # Nazwy typów z rejestru (slug → czytelna nazwa)
    type_names: dict[str, str] = {}
    try:
        from app.doc_schemas.router import get_active_schemas
        type_names = {s["slug"]: s.get("name") or s["slug"] for s in get_active_schemas(db)}
    except Exception:  # rejestr nie jest krytyczny dla cytowań
        pass

    # Pola najlepiej identyfikujące dokument (pierwsze pasujące trafia do etykiety)
    _KEY_FIELDS = ("numer_dokumentu", "numer", "numer_aneksu", "numer_zalacznika", "data")

    def wartosc_do_etykiety(v) -> str | None:
        """Odsiej wartości, które nie są treścią, tylko szablonem z formularza.

        Zdarza się, że model wyciągnie z dokumentu literał w rodzaju `${number:2}`
        (jeden taki przypadek w bazie 157 dokumentów) i wtedy w cytowaniu widać
        „Załącznik ${number:2}". Etykieta ma być czytelna, więc lepiej pokazać sam
        typ dokumentu niż śmieć.
        """
        tekst = str(v).strip()
        if not tekst or "${" in tekst or "{{" in tekst or tekst in ("-", "—", "…", "..."):
            return None
        return tekst

    for s in sources:
        # Najpierw po identyfikatorze, potem po jednoznacznej nazwie. Źródło, którego
        # nie da się przypisać pewnie, zostaje bez `file_id` — frontend pokaże wtedy
        # samą nazwę, bez klikalnego odnośnika.
        entry = po_id.get(s.get("file_id")) or by_name.get(s.get("filename"))
        if not entry:
            continue
        fid, meta = entry
        if not s.get("file_id"):
            s["file_id"] = fid
        if not isinstance(meta, dict):
            continue
        slug = meta.get("doc_type")
        if slug and slug != "inny":
            s["doc_type"] = slug
            s["doc_type_name"] = type_names.get(slug, slug)
            fields = meta.get("doc_fields") or {}
            for k in _KEY_FIELDS:
                if fields.get(k):
                    etykieta = wartosc_do_etykiety(fields[k])
                    if etykieta:
                        s["doc_key"] = etykieta
                        break
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

    # RBAC czatu (Faza C): ogranicz retrieval do folderów dozwolonych dla roli.
    # admin (readable is None) → brak filtra (widzi wszystko). Nie-admin → lista
    # dozwolonych folder_id (może być pusta = brak dostępu do niczego). Filtr po
    # `metadata.folder_id` zakłada workflow n8n (Qdrant Vector Store).
    readable = readable_folder_ids(current_user, db)
    folder_filter_enabled = readable is not None
    allowed_folder_ids = sorted(readable) if readable is not None else []
    # Sam filtr Qdranta (uprawnienia + zawężenia z pytania) buduje app/chat/zakres.py —
    # wspólnie z pomiarem `app/retrieval_bench.py`, żeby jedno nie rozjechało się z drugim.

    # Historia rozmowy budowana po naszej stronie (bez odmów) — zastępuje Simple Memory.
    # `use_history=False` = pytanie zadane „na czysto", bez wątku. Frontend prosi o to
    # przy ponowieniu po odmowie: po zmianie tematu historia poprzedniego tematu każe
    # modelowi odmówić (zmierzone: „wniosek o urlop" po rozmowie o PPK → odmowa,
    # to samo pytanie w świeżym wątku → pełna odpowiedź).
    history = build_history(db, current_user, payload.session_id) if payload.use_history else ""

    # Pytanie o ZNACZENIE POJĘCIA idzie bez historii. Zmierzone na demo (5 powtórzeń):
    # „rozwiń skrót zco" bez historii → odmowa 5/5, z historią o PPK → wymyślone
    # rozwinięcie 5/5, za każdym razem inne. Model traktuje skrót wspomniany
    # w poprzedniej turze jak byt ustalony i rozwija go z własnej wiedzy, choć
    # dokumenty milczą. Bez historii odpowiedź ma jedno źródło: treść dokumentów.
    if history and pytanie_definicyjne(payload.message):
        history = ""
        logger.info(f"[CHAT-DEFINICJA] Pytanie o pojęcie — historia odcięta: "
                    f"{payload.message[:60]!r}")

    # Zapytanie DO WYSZUKIWANIA: pytanie kontekstowe („kto go podpisał?") rozwinięte
    # na podstawie historii. Model odpowiadający dostaje nadal oryginalne pytanie.
    search_query = await condense_question(payload.message, history)
    if search_query != payload.message:
        logger.info(f"[CHAT-CONDENSE] {payload.message!r} → {search_query!r}")

    # Zakres wyszukiwania: filtr Qdranta (uprawnienia + zawężenia), wskazania ze
    # streszczeń i fragmenty dobrane z dokumentu-zwycięzcy. Cała logika w jednym
    # miejscu, wspólnym z pomiarem — zob. app/chat/zakres.py.
    from app.chat.lexical import rdzenie_z_rejestru
    from app.chat.zakres import zaplanuj_zakres
    plan = await zaplanuj_zakres(
        pytanie=payload.message,
        search_query=search_query,
        file_ids=payload.file_ids,
        folder_filter_enabled=folder_filter_enabled,
        allowed_folder_ids=allowed_folder_ids,
        # Rejestr pól opisowych czytamy tylko wtedy, gdy zawężenie leksykalne wchodzi
        # w grę — przy pytaniu o wskazane pliki byłby to zbędny przegląd bazy.
        znane_rdzenie=set() if payload.file_ids else rdzenie_z_rejestru(db),
    )
    if plan.diagnostyka:
        logger.info(f"[CHAT-STRESZCZENIE] {search_query!r}: {plan.diagnostyka}")

    # Skrót użyty w pytaniu, którego w dokumentach nie ma, wymusza na modelu zmyślenie
    # rozwinięcia (zmierzone: 4 na 6 prób dla „PPK w ZCO", za każdym razem inne).
    # Uprzedzenie modelu likwiduje to zjawisko (0 na 6), zachowując odpowiedź na
    # pozostałą część pytania — zob. app/chat/skroty.py.
    from app.chat.skroty import nieznane_skroty, uwaga_o_skrotach
    from app.qdrant_client import count_chunks_with_text
    tresc_dla_modelu = payload.message
    try:
        obce = nieznane_skroty(payload.message, count_chunks_with_text)
    except Exception as e:            # wykrywanie nie może zablokować odpowiedzi
        logger.warning(f"[CHAT-SKROTY] Sprawdzenie skrótów nieudane: {e}")
        obce = []
    if obce:
        tresc_dla_modelu += uwaga_o_skrotach(obce)
        logger.info(f"[CHAT-SKROTY] Skróty spoza dokumentów: {obce} — uprzedzam model")

    n8n_body = {
        "action": "sendMessage",
        "sessionId": f"{current_user.id}:{payload.session_id}",
        "chatInput": tresc_dla_modelu,
        "searchQuery": search_query,
        "history": history,
        "requestId": request_id,
        "sources_update_url": f"{BACKEND_CALLBACK_URL}/api/chat/sources",
        # Kolekcja TEJ instancji — jeden workflow n8n obsługuje wiele wdrożeń.
        "collection": settings.QDRANT_COLLECTION,
        "folderFilterEnabled": folder_filter_enabled,
        "allowedFolderIds": allowed_folder_ids,
        "qdrantFilter": plan.qdrant_filter,
        # Pytanie zawężone — do wskazanych dokumentów albo do fragmentów zawierających
        # rzadkie słowo z pytania. Próg trafności w n8n chroni przed odpowiadaniem
        # z przypadkowych dokumentów; przy zawężeniu tego ryzyka nie ma, a trafności są
        # z natury niższe, więc tam próg jest wtedy wyłączony.
        # Próg trafności w n8n wyłączamy tylko wtedy, gdy zakres ustalił użytkownik
        # (wskazane pliki), zawęziło go rzadkie słowo albo streszczenie zastąpiło
        # pusty kontekst. Przy samym UZUPEŁNIENIU zbioru dokumentów próg zostaje.
        "scopedToFiles": plan.scoped_to_files,
        # Fragmenty dobrane z dokumentu-zwycięzcy — n8n dokleja je do kontekstu
        # z pominięciem progu (zob. węzeł „Chunks Filter"). Pusta lista = bez zmian.
        "extraChunks": plan.dobrane,
    }
    # Migawka planu dla ewentualnej oceny użytkownika (zob. POST /api/chat/ocena)
    _purge_expired_sources()
    _diagnostyka_store[request_id] = {"ts": time.time(), "plan": {
        "sciezka": ("pliki" if payload.file_ids else
                    "terminy" if plan.terminy else
                    ("streszczenia" if plan.bez_progu else "uzupelnienie")
                    if plan.wskazane_streszczeniem else "zwykla"),
        "terminy": plan.terminy,
        "wskazane_streszczeniem": plan.wskazane_streszczeniem,
        "file_ids": payload.file_ids or [],
        "nad_progiem": sum(1 for t in plan.trafienia if t["score"] >= 0.50),
        "w_kontekscie": len(plan.w_kontekscie),
        "dobrane": [{"filename": d.get("filename"), "page": d.get("page")}
                    for d in plan.dobrane],
        "scoped_to_files": plan.scoped_to_files,
        "search_query": search_query if search_query != payload.message else None,
        "historia": bool(history),
        "wersja": get_version(),
    }}

    logger.info(
        f"[CHAT] user={current_user.username} role={current_user.role} "
        f"session={payload.session_id} req={request_id} "
        f"folderFilter={folder_filter_enabled} allowed={allowed_folder_ids} "
        f"fileIds={payload.file_ids or '-'} terminy={plan.terminy or '-'} "
        f"streszczenia={plan.wskazane_streszczeniem or '-'} "
        f"dobrane={len(plan.dobrane) or '-'} "
        f"historia={'tak' if payload.use_history else 'ODCIETA'} -> {chat_url}"
    )

    client = httpx.AsyncClient(timeout=_TIMEOUT)

    # Priorytet czatu nad parsowaniem: od teraz dyspozytor nie wyśle kolejnego
    # pliku do parsowania, aż strumień się zakończy (chat_finished w finally).
    chat_started()

    try:
        req = client.build_request("POST", chat_url, json=n8n_body, headers=outgoing_headers())
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        chat_finished()
        await client.aclose()
        logger.error(f"[CHAT] Błąd połączenia z n8n: {e}")
        raise HTTPException(status_code=502, detail=f"Nie można połączyć z czatem n8n: {e}")

    if upstream.status_code != 200:
        body = await upstream.aread()
        chat_finished()
        await upstream.aclose()
        await client.aclose()
        detail = body.decode(errors="replace")[:500]
        logger.error(f"[CHAT] n8n zwrócił {upstream.status_code}: {detail}")
        raise HTTPException(status_code=502, detail=f"Czat n8n zwrócił {upstream.status_code}: {detail}")

    async def stream_body():
        try:
            # Jedyna ingerencja w treść odpowiedzi: zdjęcie formułki o braku informacji,
            # gdy model dokleja ją do odpowiedzi, która coś jednak mówi (zob. formulka.py).
            async for kawalek in filtruj_strumien(upstream.aiter_bytes(), f" (req={request_id})"):
                yield kawalek
        finally:
            await upstream.aclose()
            await client.aclose()
            chat_finished()
            # Wznów kolejkę wstrzymaną na czas czatu (gdy to był ostatni aktywny czat).
            # Świeża sesja — sesja żądania jest już zamknięta, bo strumień leci po zwrocie.
            if not is_chat_active():
                from app.database import SessionLocal
                from app.dispatcher import try_dispatch_next
                _db = SessionLocal()
                try:
                    await try_dispatch_next(_db)
                except Exception as e:
                    logger.warning(f"[CHAT] Wznowienie kolejki po czacie nieudane: {e}")
                finally:
                    _db.close()

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


# ==================== Przepisanie pytania na samodzielne (dla wyszukiwania) ====================
# Wyszukiwanie wektorowe dostaje TYLKO bieżące pytanie, więc "kto go podpisal?" szuka
# dosłownie tej frazy — zaimek nic nie znaczy dla wyszukiwarki. Tutaj rozwijamy pytanie
# na podstawie historii; model odpowiadający dostaje nadal ORYGINALNE pytanie.
_CONDENSE_SYSTEM = (
    "Przepisujesz pytanie uzytkownika na samodzielne zapytanie do wyszukiwarki dokumentow.\n"
    "Jesli pytanie odwoluje sie do wczesniejszej rozmowy (zaimki: go, jej, ich, ten, tego, "
    "tam; skroty myslowe; domyslny podmiot), rozwin je tak, aby bylo zrozumiale BEZ kontekstu "
    "- podstaw konkretna nazwe dokumentu lub tematu z rozmowy.\n"
    "Jesli pytanie jest juz samodzielne, zwroc je BEZ ZMIAN.\n"
    "Nie odpowiadaj na pytanie i nie dodawaj wyjasnien. Zwroc wylacznie JSON zgodny ze schematem."
)

_CONDENSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "zapytanie_wyszukiwania",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"zapytanie": {"type": "string"}},
            "required": ["zapytanie"],
        },
    },
}


async def condense_question(message: str, history: str) -> str:
    """Rozwiń pytanie kontekstowe do samodzielnego (tylko na potrzeby wyszukiwania).

    Zwraca oryginalne pytanie przy braku historii lub jakimkolwiek problemie —
    wyszukiwanie nigdy nie traci na tej funkcji, może tylko zyskać.
    """
    import json as _json

    if not history.strip() or not message.strip():
        return message

    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 120,
        "messages": [
            {"role": "system", "content": _CONDENSE_SYSTEM},
            {"role": "user", "content": f"DOTYCHCZASOWA ROZMOWA:\n{history}\n\nPYTANIE: {message}"},
        ],
        "response_format": _CONDENSE_FORMAT,
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0)
        ) as client:
            resp = await client.post(url, json=body)
        resp.raise_for_status()
        out = _json.loads(resp.json()["choices"][0]["message"]["content"]).get("zapytanie")
    except Exception as e:
        logger.warning(f"[CHAT-CONDENSE] Przepisanie pytania nieudane: {e}")
        return message

    out = (out or "").strip()
    # Zabezpieczenie: model bywa gadatliwy — odrzuć podejrzanie długie przeróbki
    if not out or len(out) > 300:
        return message
    return out


class RouteRequest(BaseModel):
    message: str


_ROUTE_SYSTEM = (
    "Klasyfikujesz wypowiedz uzytkownika w systemie dokumentow firmowych.\n"
    "LISTA = uzytkownik chce ZOBACZYC, ZNALEZC, WSKAZAC lub POLICZYC dokumenty. Naleza tu:\n"
    " - polecenia: pokaz, znajdz, wyszukaj, wylistuj, wypisz, podaj, otworz, daj "
    "(np. pokaz regulamin wynagradzania)\n"
    " - pytania o zbior dokumentow: wszystkie zarzadzenia; jakie umowy z 2023; ile jest wnioskow\n"
    " - sama nazwa RODZAJU dokumentow, zwlaszcza w liczbie mnogiej (np. regulaminy; "
    "zarzadzenia; wnioski; instrukcje), albo rodzaj z warunkiem (zarzadzenia z 2024; "
    "wnioski Kowalskiej)\n"
    " - pytania o dokumenty POWIAZANE Z OSOBA: kto co opracowal, sprawdzil, zatwierdzil, "
    "podpisal lub wydal, oraz czy dana osoba ma jakies dokumenty. Tu decyduje temat, "
    "nie forma pytania (np. czy Kowalska zatwierdzila jakies instrukcje; instrukcje "
    "zatwierdzone przez Kowalska; zarzadzenia podpisane przez dyrektora)\n"
    "TRESC = uzytkownik pyta o to, CO JEST W dokumentach: tresc, zasady, definicje, "
    "konkretne wartosci. Naleza tu:\n"
    " - SAMA NAZWA JEDNEGO, KONKRETNEGO dokumentu, bez polecenia i bez slowa pytajacego "
    "(np. wniosek o urlop opiekunczy; regulamin wynagradzania; polecenie wyjazdu sluzbowego; "
    "zarzadzenie 30/2024). Uzytkownik chce wiedziec, czym ten dokument jest — odpowiedz z "
    "tresci zawiera odnosnik do niego, wiec dostaje tez sam dokument.\n"
    " - pytania zaczynajace sie od: co, jak, kto, kiedy, ile wynosi, czy, dlaczego, gdzie znajde\n"
    " - przyklady: co jest w regulaminie wynagradzania; jak przejsc na prace zdalna; "
    "ile wynosi dodatek stazowy;\n"
    "   jaka kategorie zaszeregowania ma sanitariusz\n"
    " - UWAGA: pytanie o pole opisowe KONKRETNEGO, nazwanego dokumentu to TRESC "
    "(np. kto zatwierdzil instrukcje opieki pielegniarskiej) — odpowiedz jest w jego naglowku. "
    "Dopiero pytanie o ZBIOR dokumentow danej osoby to LISTA.\n"
    "W razie watpliwosci: jesli wypowiedz to POLECENIE albo nazwa RODZAJU dokumentow "
    "(liczba mnoga) -> LISTA; jesli to nazwa JEDNEGO dokumentu albo pytanie o wiedze -> TRESC.\n"
    "Osobno oceniasz pole 'poprzednie': ustaw true, gdy wypowiedz odnosi sie do dokumentow "
    "wskazanych we WCZESNIEJSZEJ odpowiedzi, zamiast opisywac je od nowa. Sygnalem sa "
    "zaimki i odwolania bez wlasnej tresci: 'co jest w tym dokumencie', 'w nim', "
    "'w tych dokumentach', 'w pierwszym z nich', 'wypisz je', 'je wszystkie', "
    "'ktory z nich', 'ile ich jest', 'a co dalej'. "
    "Gdy wypowiedz sama okresla, o jakie dokumenty chodzi, ustaw false.\n"
    "Zwroc wylacznie JSON zgodny ze schematem."
)

_ROUTE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "typ_pytania",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "typ": {"type": "string", "enum": ["LISTA", "TRESC"]},
                "poprzednie": {"type": "boolean"},
            },
            "required": ["typ", "poprzednie"],
        },
    },
}


@router.post("/route")
async def route_question(
    payload: RouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rozpoznaj typ pytania: LISTA (wypisz dokumenty) czy TRESC (odpowiedź z treści).

    Mini-wywołanie modelu (8–9 tokenów wyjścia, ~0,4 s). ZASADA BEZPIECZEŃSTWA: przy
    jakimkolwiek problemie (brak schematów, awaria modelu, zła odpowiedź) zwracamy
    TRESC — czyli dotychczasowe zachowanie czatu. Router może tylko poprawić UX,
    nigdy go nie zepsuć.
    """
    import json as _json

    # Bez rejestru ścieżka LISTA nie ma sensu (nie ma po czym filtrować)
    from app.doc_schemas.router import get_active_schemas
    if not get_active_schemas(db):
        return {"mode": "TRESC", "reason": "brak schematów"}

    text = (payload.message or "").strip()
    if not text:
        return {"mode": "TRESC", "reason": "puste pytanie"}

    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 24,  # dwa pola JSON (typ + poprzednie)
        "messages": [
            {"role": "system", "content": _ROUTE_SYSTEM},
            {"role": "user", "content": text},
        ],
        "response_format": _ROUTE_FORMAT,
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)) as client:
            resp = await client.post(url, json=body)
        resp.raise_for_status()
        parsed = _json.loads(resp.json()["choices"][0]["message"]["content"])
        mode = parsed.get("typ")
        refers_back = bool(parsed.get("poprzednie"))
    except Exception as e:
        logger.warning(f"[CHAT-ROUTE] Rozpoznanie typu pytania nieudane: {e}")
        return {"mode": "TRESC", "refers_to_previous": False, "reason": "błąd rozpoznania"}

    if mode not in ("LISTA", "TRESC"):
        mode = "TRESC"
    logger.info(
        f"[CHAT-ROUTE] user={current_user.username} → {mode}"
        f"{' (do poprzednich)' if refers_back else ''}: {text[:60]}"
    )
    return {"mode": mode, "refers_to_previous": refers_back}


@router.get("/parse-active")
def parse_active(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Czy trwa teraz parsowanie pliku (dzieli model z czatem).

    Frontend pokazuje na tej podstawie komunikat, że odpowiedź może chwilę
    poczekać (czat i parsowanie współdzielą model vLLM). Dostępne dla każdego
    zalogowanego — nie ujawnia treści, tylko fakt zajętości.
    """
    from app.models import File as FileModel, DocumentStatus
    active = (
        db.query(FileModel)
        .filter(FileModel.status == DocumentStatus.PROCESSING)
        .count()
    ) > 0
    return {"active": active}


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
    """Zapisz jedną turę: pytanie użytkownika + odpowiedź asystenta.

    Zwraca identyfikatory zapisanych wiadomości — frontend potrzebuje identyfikatora
    odpowiedzi, żeby przypiąć do niej ocenę użytkownika.
    """
    conv = _get_owned_conversation(conv_id, current_user, db)
    pytanie = Message(conversation_id=conv.id, role="user", content=payload.user_message)
    odpowiedz = Message(
        conversation_id=conv.id, role="assistant",
        content=payload.assistant_message, sources=payload.sources or None,
    )
    db.add(pytanie)
    db.add(odpowiedz)
    # dotknij updated_at (żeby rozmowa wskoczyła na górę listy)
    conv.updated_at = datetime.utcnow()
    db.commit()
    return {
        "message": "Tura zapisana",
        "conversation_id": conv.id,
        "user_message_id": pytanie.id,
        "assistant_message_id": odpowiedz.id,
    }


# ==================== Ocena odpowiedzi ====================
# Po co to istnieje: najgroźniejszy błąd tego systemu jest z danych NIEWIDOCZNY.
# Odpowiedź może być płynna, powoływać się na prawdziwy fragment prawdziwego dokumentu
# i mimo to być nieprawdziwa — bo fragment pochodzi z dokumentu o czymś innym (zmierzony
# przypadek: pytanie o „gruszę" dostało wiek dziecka z polisy ubezpieczeniowej).
# Automatycznie umiemy wskazać co najwyżej PODEJRZANE odpowiedzi; rozstrzygnąć może
# tylko ten, kto zna prawidłową odpowiedź.
OCENY_DOZWOLONE = {"dobra", "neutralna", "zla"}

# Powody podawane jednym kliknięciem przy ocenie negatywnej. Każdy wskazuje inną
# część systemu, więc samo zliczanie ich mówi, gdzie szukać przyczyny.
POWODY = {
    "nieprawda": "nieprawdziwa informacja",        # model albo zły dokument
    "nie_znalazl": "nie znalazł, a powinien",      # wyszukiwanie
    "niepelna": "niepełna odpowiedź",              # kontekst przycięty albo prompt
    "nie_o_to": "nie o to pytałem",                # rozumienie pytania
}


@router.get("/ocena/konfiguracja")
def ocena_konfiguracja(current_user: User = Depends(get_current_user)):
    """Czy pokazywać prośbę o ocenę i jakie powody zaproponować."""
    return {
        "wlaczone": settings.OCENY_ODPOWIEDZI,
        "powody": [{"kod": k, "etykieta": v} for k, v in POWODY.items()],
    }


@router.post("/ocena", status_code=201)
def zapisz_ocene(
    payload: OcenaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zapisz ocenę odpowiedzi wraz z migawką planu wyszukiwania."""
    if payload.ocena not in OCENY_DOZWOLONE:
        raise HTTPException(status_code=400, detail=f"Nieznana ocena: {payload.ocena}")
    powod = payload.powod if payload.powod in POWODY else None

    diagnostyka = None
    if payload.request_id:
        wpis = _diagnostyka_store.get(payload.request_id)
        diagnostyka = dict(wpis["plan"]) if wpis else None
        zrodla = _sources_store.get(payload.request_id)
        if diagnostyka is not None and zrodla:
            diagnostyka["zrodla"] = zrodla["sources"]

    # JEDNA ocena na odpowiedź: kolejne kliknięcie NADPISUJE poprzednie. Użytkownik
    # ma prawo zmienić zdanie albo trafić w niewłaściwą ikonę, a zapis każdej próby
    # zaśmieciłby materiał do analizy ocenami, których nikt nie zamierzał wystawić.
    # Dopisanie powodu do oceny negatywnej to drugie kliknięcie tej samej oceny —
    # więc bez nadpisywania każde zgłoszenie liczyłoby się podwójnie.
    kopia_pytania = (payload.pytanie or "")[:4000] or None
    zapytanie = db.query(OcenaOdpowiedzi).filter(OcenaOdpowiedzi.user_id == current_user.id)
    istniejaca = None
    if payload.message_id is not None:
        istniejaca = zapytanie.filter(
            OcenaOdpowiedzi.message_id == payload.message_id).first()
    if istniejaca is None and kopia_pytania:
        # Pierwsze kliknięcie potrafi wyprzedzić zapis historii rozmowy, więc ocena
        # bez `message_id` powstaje WCZEŚNIEJ niż identyfikator, którym dałoby się ją
        # odnaleźć. Wtedy rozpoznajemy ją po treści pytania tego samego użytkownika.
        # Ograniczenie: dwa identyczne pytania bez zapisanej historii nadpiszą się
        # nawzajem — przypadek rzadki i mniej szkodliwy niż mnożenie ocen.
        istniejaca = (zapytanie
                      .filter(OcenaOdpowiedzi.message_id.is_(None),
                              OcenaOdpowiedzi.pytanie == kopia_pytania)
                      .order_by(OcenaOdpowiedzi.id.desc()).first())

    if istniejaca is not None:
        istniejaca.ocena = payload.ocena
        istniejaca.powod = powod
        if payload.message_id is not None:
            istniejaca.message_id = payload.message_id   # dopisz, gdy już się pojawił
        if diagnostyka:
            istniejaca.diagnostyka = diagnostyka
        ocena = istniejaca
        zmiana = "zmieniona"
    else:
        ocena = OcenaOdpowiedzi(
            message_id=payload.message_id,
            user_id=current_user.id,
            ocena=payload.ocena,
            powod=powod,
            # Kopia treści: rozmowę można skasować, a zgłoszenie ma przeżyć i posłużyć
            # za materiał do zestawu kontrolnego.
            pytanie=kopia_pytania,
            odpowiedz=(payload.odpowiedz or "")[:8000] or None,
            diagnostyka=diagnostyka,
        )
        db.add(ocena)
        zmiana = "nowa"
    db.commit()
    logger.info(
        f"[CHAT-OCENA] user={current_user.username} {payload.ocena} ({zmiana})"
        f"{f' powod={powod}' if powod else ''} req={payload.request_id or '-'} "
        f"sciezka={(diagnostyka or {}).get('sciezka', '?')}"
    )
    return {"message": "Dziękujemy za ocenę.", "id": ocena.id}


@router.get("/rejestr")
def rejestr_pytan(
    limit: int = 100,
    tylko_ocenione: bool = False,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rejestr zadanych pytań wraz z odpowiedziami i ewentualną oceną (administracja).

    Po co, skoro są już oceny: w fazie testów najwięcej mówi to, o co ludzie PYTAJĄ —
    także wtedy (a może zwłaszcza wtedy), gdy nikt nie kliknął oceny. Rejestr pokazuje
    pełny ruch, a przełącznik `tylko_ocenione` zawęża go do zgłoszeń.

    Czego tu NIE MA: migawki planu wyszukiwania dla pytań NIEOCENIONYCH. Powstaje ona
    w pamięci procesu z krótkim czasem życia i trafia do bazy dopiero razem z oceną.
    Zapisywanie jej dla każdego pytania to osobna decyzja — kosztuje miejsce przy
    każdej rozmowie, a przydaje się tylko przy tych, które budzą wątpliwość.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator.")

    limit = max(1, min(limit, 500))
    # Jedno zapytanie zamiast N+1: bierzemy z zapasem, bo tura to dwie wiadomości.
    zapytanie = (
        db.query(Message, Conversation.user_id, User.username, User.full_name, User.role)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .outerjoin(User, Conversation.user_id == User.id)
    )
    if user_id is not None:
        zapytanie = zapytanie.filter(Conversation.user_id == user_id)
    wiadomosci = zapytanie.order_by(Message.id.desc()).limit(limit * 3).all()
    # Pytanie to najbliższa POPRZEDZAJĄCA wiadomość użytkownika w tej samej rozmowie.
    pary: list[dict] = []
    for msg, uid, username, full_name, rola in wiadomosci:      # malejąco po id
        if msg.role == "assistant":
            pary.append({"msg": msg, "username": username, "full_name": full_name,
                         "rola": rola.value if rola else None, "user_id": uid})
        else:
            # Idziemy od najnowszych, więc pytanie napotykamy PO swojej odpowiedzi.
            for p in pary:
                if p["msg"].conversation_id == msg.conversation_id and "pytanie" not in p:
                    p["pytanie"] = msg.content
                    break

    oceny_wg_msg = {
        o.message_id: o for o in
        db.query(OcenaOdpowiedzi)
        .filter(OcenaOdpowiedzi.message_id.in_([p["msg"].id for p in pary] or [0]))
        .all()
    }

    wynik = []
    for p in pary:
        ocena = oceny_wg_msg.get(p["msg"].id)
        if tylko_ocenione and ocena is None:
            continue
        wynik.append({
            "message_id": p["msg"].id,
            "pytanie": p.get("pytanie"),
            "odpowiedz": (p["msg"].content or "")[:600],
            # Pełne źródła, nie same nazwy — rejestr ma pozwalać OTWORZYĆ dokument,
            # tak jak lista pod odpowiedzią w Bazie wiedzy. Bez `file_id` nie da się.
            "zrodla": [{"filename": s.get("filename"), "page": s.get("page"),
                        "file_id": s.get("file_id"), "cited": s.get("cited")}
                       for s in (p["msg"].sources or []) if isinstance(s, dict)][:8],
            "uzytkownik": p["full_name"] or p["username"],
            "user_id": p["user_id"],
            "rola": p["rola"],
            "created_at": p["msg"].created_at,
            "ocena": ocena.ocena if ocena else None,
            "powod": POWODY.get(ocena.powod, None) if ocena and ocena.powod else None,
            "diagnostyka": ocena.diagnostyka if ocena else None,
        })
        if len(wynik) >= limit:
            break

    # Ile pytań zadała każda rola — po to, żeby zobaczyć, kto z systemu korzysta.
    wg_roli: dict[str, int] = {}
    for p in pary:
        klucz = p["rola"] or "?"
        wg_roli[klucz] = wg_roli.get(klucz, 0) + 1

    return {"wg_roli": wg_roli, "pytania": wynik}


@router.get("/oceny")
def lista_ocen(
    limit: int = 100,
    tylko_negatywne: bool = False,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zestawienie ocen dla administratora — materiał na zestaw kontrolny."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator.")
    zapytanie = db.query(OcenaOdpowiedzi)
    if tylko_negatywne:
        zapytanie = zapytanie.filter(OcenaOdpowiedzi.ocena == "zla")
    if user_id is not None:
        zapytanie = zapytanie.filter(OcenaOdpowiedzi.user_id == user_id)
    wiersze = zapytanie.order_by(OcenaOdpowiedzi.id.desc()).limit(min(limit, 500)).all()

    # Podsumowanie liczy to samo, co pokazuje lista — inaczej po zawężeniu do jednej
    # osoby licznik nad tabelą mówiłby o kimś innym niż wiersze pod nim.
    podsumowanie: dict[str, int] = {}
    pod_zapytanie = db.query(OcenaOdpowiedzi.ocena)
    if user_id is not None:
        pod_zapytanie = pod_zapytanie.filter(OcenaOdpowiedzi.user_id == user_id)
    for o in pod_zapytanie.all():
        podsumowanie[o[0]] = podsumowanie.get(o[0], 0) + 1

    autorzy = {u.id: (u.full_name or u.username) for u in db.query(User).all()}
    return {
        "podsumowanie": podsumowanie,
        "oceny": [{
            "id": o.id,
            "ocena": o.ocena,
            "powod": POWODY.get(o.powod or "", None),
            "pytanie": o.pytanie,
            "odpowiedz": (o.odpowiedz or "")[:400],
            "diagnostyka": o.diagnostyka,
            "uzytkownik": autorzy.get(o.user_id),
            "created_at": o.created_at,
        } for o in wiersze],
    }


@router.get("/uzytkownicy-pytajacy")
def uzytkownicy_pytajacy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Osoby, które zadały choć jedno pytanie — do filtra w zestawieniach.

    Bierzemy je z ROZMÓW, a nie z listy wszystkich kont: filtr ma pokazywać tych,
    dla których w ogóle jest co filtrować.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator.")
    wiersze = (
        db.query(User.id, User.username, User.full_name, User.role)
        .join(Conversation, Conversation.user_id == User.id)
        .distinct()
        .all()
    )
    return {"uzytkownicy": [
        {"id": i, "nazwa": full or username, "rola": rola.value if rola else None}
        for i, username, full, rola in sorted(wiersze, key=lambda w: (w[2] or w[1] or "").lower())
    ]}


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
