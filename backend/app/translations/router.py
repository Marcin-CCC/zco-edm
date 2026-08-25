"""Poprawki tłumaczeń interfejsu — odczyt dla frontu, edycja dla administratora.

Podział pracy: katalogi `frontend/messages/*.json` jadą z obrazem i są punktem
wyjścia, a ta tabela trzyma WYŁĄCZNIE to, co ktoś poprawił po zobaczeniu tekstu
w działającym interfejsie. Dzięki temu wdrożenie klienckie poprawia swoje napisy
bez wydania nowej wersji, a wydanie nowej wersji nie kasuje cudzych poprawek.

Backend NIE zna katalogów. Nie może ich znać: leżą w obrazie frontendu, nie tutaj.
Zna wyłącznie nadpisania, a zestawienie „co jest przetłumaczone, a co nie" składa
ekran administratora, który ma katalogi u siebie. Kopiowanie plików do obrazu
backendu dawałoby dwie prawdy rozjeżdżające się przy pierwszym wydaniu.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.locales import BASE_LOCALE, SUPPORTED_LOCALES, normalize_locale
from app.models import Translation, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translations", tags=["translations"])

# Tłumaczenie maszynowe idzie partiami. Model gubi się przy długich listach, a jedno
# żądanie na napis kosztowałoby kilkaset przebiegów — 20 to zmierzony kompromis.
ROZMIAR_PARTII = 20
_TIMEOUT = httpx.Timeout(120.0)


class TranslationIn(BaseModel):
    locale: str
    key: str
    value: str


class AutoItem(BaseModel):
    key: str
    source: str


class AutoIn(BaseModel):
    locale: str
    items: list[AutoItem]


def _sprawdz_jezyk(locale: str) -> str:
    kod = normalize_locale(locale)
    if kod is None:
        raise HTTPException(
            status_code=400,
            detail=f"Nieobsługiwany język. Dostępne: {', '.join(SUPPORTED_LOCALES)}.",
        )
    if kod == BASE_LOCALE:
        raise HTTPException(
            status_code=400,
            detail="Polski jest językiem bazowym — jego teksty zmienia się w kodzie, nie tutaj.",
        )
    return kod


def _tylko_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zmieniać tłumaczenia.")


@router.get("/{locale}")
def read_overrides(locale: str, db: Session = Depends(get_db)):
    """Nadpisania dla języka: `{klucz: wartość}`.

    BEZ uwierzytelnienia, bo woła to serwer Next.js przy renderowaniu KAŻDEJ strony —
    także ekranu logowania, gdzie nie ma jeszcze żadnej sesji. Zawartością są napisy
    interfejsu, te same, które i tak widać na ekranie.
    """
    kod = normalize_locale(locale)
    if kod is None or kod == BASE_LOCALE:
        return {}
    wiersze = db.query(Translation).filter(Translation.locale == kod).all()
    return {w.key: w.value for w in wiersze}


@router.get("/{locale}/meta")
def read_overrides_meta(
    locale: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """To samo, ale z metryczką — dla ekranu administratora.

    `source` mówi, czy napis wpisał człowiek, czy przetłumaczył model. Bez tego
    tłumacz nie odróżniłby tekstu sprawdzonego od maszynowego i musiałby czytać
    wszystko od nowa po każdym uruchomieniu tłumaczenia.
    """
    _tylko_admin(current_user)
    kod = _sprawdz_jezyk(locale)
    wiersze = db.query(Translation).filter(Translation.locale == kod).all()
    return {
        w.key: {
            "value": w.value,
            "source": w.source,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
        }
        for w in wiersze
    }


def _zapisz(db: Session, kod: str, key: str, value: str, source: str, user_id: int) -> Translation:
    wiersz = db.query(Translation).filter(
        Translation.locale == kod, Translation.key == key
    ).first()
    if wiersz is None:
        wiersz = Translation(locale=kod, key=key)
        db.add(wiersz)
    wiersz.value = value
    wiersz.source = source
    wiersz.updated_by = user_id
    return wiersz


@router.put("")
def upsert_override(
    payload: TranslationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zapis poprawki. Pusta wartość KASUJE wiersz — powrót do tekstu z katalogu.

    Pustego napisu nie zapisujemy nigdy: byłby nie do odróżnienia od „przetłumaczone
    na nic" i zostawiałby w interfejsie puste miejsce zamiast polskiego zdania.
    """
    _tylko_admin(current_user)
    kod = _sprawdz_jezyk(payload.locale)
    klucz = payload.key.strip()
    if not klucz:
        raise HTTPException(status_code=400, detail="Pusty klucz.")
    if len(klucz) > 200:
        raise HTTPException(status_code=400, detail="Klucz może mieć najwyżej 200 znaków.")

    wartosc = payload.value.strip()
    if not wartosc:
        db.query(Translation).filter(
            Translation.locale == kod, Translation.key == klucz
        ).delete()
        db.commit()
        return {"locale": kod, "key": klucz, "value": None}

    _zapisz(db, kod, klucz, wartosc, "human", current_user.id)
    db.commit()
    logger.info(f"[TŁUMACZENIA] {current_user.username} poprawił {kod}:{klucz}")
    return {"locale": kod, "key": klucz, "value": wartosc, "source": "human"}


@router.delete("/{locale}/{key}")
def delete_override(
    locale: str,
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Skasowanie poprawki — napis wraca do tego z katalogu w obrazie."""
    _tylko_admin(current_user)
    kod = _sprawdz_jezyk(locale)
    usuniete = db.query(Translation).filter(
        Translation.locale == kod, Translation.key == key
    ).delete()
    db.commit()
    return {"deleted": usuniete}


SYSTEM_TLUMACZA = (
    "Jesteś tłumaczem interfejsu aplikacji do zarządzania dokumentacją medyczną.\n"
    "Tłumaczysz KRÓTKIE napisy interfejsu: etykiety przycisków, nagłówki kolumn,\n"
    "komunikaty. Zasady:\n"
    "- Zwróć WYŁĄCZNIE tłumaczenie, bez cudzysłowów, bez komentarza, bez kropki na\n"
    "  końcu, jeśli w oryginale jej nie ma.\n"
    "- Zachowaj wielkość liter tak, jak przyjęto w interfejsach w języku docelowym.\n"
    "- Fragmenty w nawiasach klamrowych, np. {count}, PRZEPISZ dokładnie — to miejsca\n"
    "  na wartości podstawiane przez program.\n"
    "- Nie tłumacz nazw własnych aplikacji ani nazw plików.\n"
    "- Napis ma być tak krótki jak oryginał: dłuższy nie zmieści się w przycisku."
)

NAZWY_JEZYKOW = {"en": "angielski", "pl": "polski"}


async def _przetlumacz_partie(kod: str, teksty: list[str]) -> list[str]:
    """Jedna partia napisów. Numerowanie po obu stronach, bo model gubi kolejność."""
    ponumerowane = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(teksty))
    prompt = (
        f"Przetłumacz na język {NAZWY_JEZYKOW.get(kod, kod)} poniższe napisy interfejsu.\n"
        f"Zwróć DOKŁADNIE {len(teksty)} linii w tej samej kolejności i z tymi samymi\n"
        f"numerami, w postaci „numer. tłumaczenie”. Nic poza tymi liniami.\n\n"
        f"{ponumerowane}"
    )
    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0.1,
        "max_tokens": 40 * len(teksty) + 200,
        "messages": [
            {"role": "system", "content": SYSTEM_TLUMACZA},
            {"role": "user", "content": prompt},
        ],
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    tresc = (resp.json()["choices"][0]["message"]["content"] or "").strip()

    # Odczyt po numerach, a nie po kolejności linii: model bywa gadatliwy i dokłada
    # wstęp albo pustą linię. Numer wiąże tłumaczenie z napisem, więc zgubiona linia
    # zostawia dziurę do uzupełnienia ręcznie, zamiast przesuwać całą resztę.
    wynik: list[str] = [""] * len(teksty)
    for linia in tresc.split("\n"):
        linia = linia.strip()
        if not linia or "." not in linia:
            continue
        numer, _, reszta = linia.partition(".")
        if not numer.strip().isdigit():
            continue
        i = int(numer.strip()) - 1
        if 0 <= i < len(teksty):
            wynik[i] = reszta.strip().strip('"').strip()
    return wynik


@router.post("/auto")
async def machine_translate(
    payload: AutoIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tłumaczenie maszynowe wskazanych napisów — pierwszy przebieg dla nowego języka.

    Wynik zapisuje się jako `source = "machine"`, więc na ekranie administratora widać,
    czego człowiek jeszcze nie sprawdził. Napisów, które model pominął, NIE zgadujemy —
    zostają nieprzetłumaczone i widać je na liście.

    Które napisy tłumaczyć, wskazuje ekran administratora: to on ma katalogi i wie,
    czego brakuje.
    """
    _tylko_admin(current_user)
    kod = _sprawdz_jezyk(payload.locale)
    if not payload.items:
        return {"translated": {}, "failed": []}
    if len(payload.items) > 500:
        raise HTTPException(status_code=400, detail="Najwyżej 500 napisów naraz.")

    przetlumaczone: dict[str, str] = {}
    nieudane: list[str] = []
    for start in range(0, len(payload.items), ROZMIAR_PARTII):
        partia = payload.items[start:start + ROZMIAR_PARTII]
        try:
            wyniki = await _przetlumacz_partie(kod, [p.source for p in partia])
        except Exception as e:                       # awaria modelu nie może zjeść partii
            logger.error(f"[TŁUMACZENIA] Partia od {start} nieudana: {e}")
            nieudane.extend(p.key for p in partia)
            continue
        for pozycja, wynik in zip(partia, wyniki):
            if wynik:
                _zapisz(db, kod, pozycja.key, wynik, "machine", current_user.id)
                przetlumaczone[pozycja.key] = wynik
            else:
                nieudane.append(pozycja.key)

    db.commit()
    logger.info(
        f"[TŁUMACZENIA] {current_user.username}: {kod} — przetłumaczono "
        f"{len(przetlumaczone)}, nie udało się {len(nieudane)}"
    )
    return {"translated": przetlumaczone, "failed": nieudane}
