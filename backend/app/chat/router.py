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
from app.models import User, File as FileModel, Conversation, Message
from app.schemas import (
    ChatRequest, ChatSourcesPayload,
    ConversationCreate, ConversationSummary, ConversationDetail, MessageOut, TurnCreate,
)
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
    """Dopasuj file_id po nazwie pliku (link do pobrania) + dołóż typ dokumentu.

    Faza B (#7): źródła pokazują też rozpoznany typ i kluczowe pola (numer/data),
    więc zamiast samej nazwy pliku użytkownik widzi np. „Zarządzenie nr 8/2023".
    Dane bierzemy z `files.metadata_` (Postgres) — bez zmian w n8n.
    """
    filenames = {s.get("filename") for s in sources if s.get("filename")}
    if not filenames:
        return sources
    rows = (
        db.query(FileModel.id, FileModel.filename, FileModel.metadata_)
        .filter(FileModel.filename.in_(filenames))
        .all()
    )
    by_name = {filename: (fid, meta) for fid, filename, meta in rows}

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
        entry = by_name.get(s.get("filename"))
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
    # Gotowy filtr Qdranta dla węzła Vector Store (options.searchFilterJson).
    # admin → None (brak filtra, widzi wszystko, w tym pliki z roota bez folder_id).
    # nie-admin → dopuszczaj tylko chunki z dozwolonych folderów (match.any).
    # Pusta lista → match.any:[] → nic nie pasuje (brak uprawnień = brak wyników).
    warunki: list[dict] = []
    if folder_filter_enabled:
        warunki.append({"key": "metadata.folder_id", "match": {"any": allowed_folder_ids}})
    # Same uprawnienia, bez zawężeń wynikających z treści pytania. Dobór z dokumentu
    # -zwycięzcy szuka właśnie z tym filtrem: zawężenie po rzadkim słowie ma wskazać
    # DOKUMENT, a nie ograniczać, którą jego stronę wolno przeczytać (zob. dobor.py).
    warunki_rbac = list(warunki)

    # Zawężenie do konkretnych dokumentów (pytanie o treść wskazanych wcześniej plików).
    # Dokłada się do warunku uprawnień, więc nie da się nim obejść RBAC — najwyżej
    # zawęzić do części tego, co i tak wolno czytać.
    terminy: list[str] = []
    if payload.file_ids:
        warunki.append({"key": "metadata.file_id", "match": {"any": sorted(set(payload.file_ids))}})
    else:
        # Zawężenie po nazwie własnej. Wyszukiwanie semantyczne nie znajduje nazwisk
        # (mierzone: właściwe fragmenty 0,28–0,40, niżej niż przypadkowe), więc rzadkie
        # słowo z pytania dokładamy jako warunek dosłowny. Warunki łączymy przez `should`
        # — chunk ma zawierać KTÓREKOLWIEK z rzadkich słów, bo imię i nazwisko potrafią
        # trafić do różnych fragmentów.
        from app.chat.lexical import rdzenie_z_rejestru, terminy_selektywne
        from app.qdrant_client import count_chunks_with_text, count_points
        terminy = terminy_selektywne(
            payload.message, count_chunks_with_text, count_points(), rdzenie_z_rejestru(db)
        )
        if terminy:
            warunki.append({"should": [
                {"key": "content", "match": {"text": t}} for t in terminy
            ]})

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

    # Pytanie zadane potocznie: gdy zwykłe fragmenty nie przekraczają progu, wskaż
    # dokumenty po ich streszczeniach i zawęź do nich wyszukiwanie. Odpowiedź nadal
    # powstaje z oryginalnych fragmentów — streszczenie tylko wskazuje dokument.
    wskazane_streszczeniem: list[int] = []
    bez_progu = False
    wektor_pytania: list[float] | None = None
    if not payload.file_ids:
        # Jedno osadzenie pytania na dwóch odbiorców: wskazywanie po streszczeniach
        # i dobór z dokumentu-zwycięzcy. Awaria = obie ścieżki po prostu nie działają.
        from app.summaries import wektor as osadz
        try:
            wektor_pytania = await osadz(search_query)
        except Exception as e:
            logger.warning(f"[CHAT] Osadzenie pytania nieudane: {e}")
    if not payload.file_ids and not terminy:
        from app.chat.streszczenia import wskaz_dokumenty
        wskazane_streszczeniem, bez_progu, diagnostyka = await wskaz_dokumenty(
            search_query,
            {"must": warunki} if warunki else None,
            allowed_folder_ids if folder_filter_enabled else None,
            wektor_pytania=wektor_pytania,
        )
        logger.info(f"[CHAT-STRESZCZENIE] {search_query!r}: {diagnostyka}")
        if wskazane_streszczeniem:
            warunki.append(
                {"key": "metadata.file_id", "match": {"any": wskazane_streszczeniem}}
            )

    qdrant_filter = {"must": warunki} if warunki else None

    # Pytanie o złożonym ciągu rozumowania („w jakim wieku dzieci mogą korzystać
    # z wczasów pod gruszą?"): dokument jest rozpoznany dobrze, ale kryterium leży
    # na innej stronie niż opis świadczenia i nie mieści się w progu. Dokładamy
    # fragmenty z dokumentu-zwycięzcy pod niepokrytą część pytania — zob. dobor.py.
    # Pomijamy tylko wtedy, gdy zakres wskazał UŻYTKOWNIK (pytanie o konkretne pliki)
    # albo gdy nie udało się osadzić pytania.
    dobrane: list[dict] = []
    if wektor_pytania is not None:
        from app.chat.dobor import dobierz_fragmenty
        from app.chat.streszczenia import PROG_FRAGMENTU
        from app.qdrant_client import search_chunks_full
        from app.summaries import wektor as osadz
        try:
            trafienia = search_chunks_full(wektor_pytania, qdrant_filter, limit=15)
            # Odwzorowanie węzła „Chunks Filter": przy zawężonym wyszukiwaniu próg
            # jest wyłączony i do kontekstu wchodzi wszystko, inaczej — tylko to,
            # co przekroczyło próg. Dobór musi liczyć na TYM SAMYM zbiorze.
            w_kontekscie = (
                trafienia if (terminy or bez_progu)
                else [t for t in trafienia if t["score"] >= PROG_FRAGMENTU]
            )
            dobrane = await dobierz_fragmenty(
                search_query,
                w_kontekscie,
                {"must": warunki_rbac} if warunki_rbac else None,
                osadz,
                search_chunks_full,
            )
        except Exception as e:      # dobór nie może zablokować odpowiedzi
            logger.warning(f"[CHAT-DOBOR] Dobór fragmentów nieudany: {e}")

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
        "qdrantFilter": qdrant_filter,
        # Pytanie zawężone — do wskazanych dokumentów albo do fragmentów zawierających
        # rzadkie słowo z pytania. Próg trafności w n8n chroni przed odpowiadaniem
        # z przypadkowych dokumentów; przy zawężeniu tego ryzyka nie ma, a trafności są
        # z natury niższe, więc tam próg jest wtedy wyłączony.
        # Próg trafności w n8n wyłączamy tylko wtedy, gdy zakres ustalił użytkownik
        # (wskazane pliki), zawęziło go rzadkie słowo albo streszczenie zastąpiło
        # pusty kontekst. Przy samym UZUPEŁNIENIU zbioru dokumentów próg zostaje.
        "scopedToFiles": bool(payload.file_ids or terminy or bez_progu),
        # Fragmenty dobrane z dokumentu-zwycięzcy — n8n dokleja je do kontekstu
        # z pominięciem progu (zob. węzeł „Chunks Filter"). Pusta lista = bez zmian.
        "extraChunks": dobrane,
    }
    logger.info(
        f"[CHAT] user={current_user.username} role={current_user.role.value} "
        f"session={payload.session_id} req={request_id} "
        f"folderFilter={folder_filter_enabled} allowed={allowed_folder_ids} "
        f"fileIds={payload.file_ids or '-'} terminy={terminy or '-'} "
        f"streszczenia={wskazane_streszczeniem or '-'} "
        f"dobrane={len(dobrane) or '-'} "
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
