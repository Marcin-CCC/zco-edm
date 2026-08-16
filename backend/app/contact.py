"""Zgłoszenia do wsparcia technicznego z ekranu „Skontaktuj się".

Wysyłamy własnym SMTP-em, a nie przez n8n. Powód: n8n obsługuje przetwarzanie
dokumentów i jego awaria nie powinna odcinać drogi zgłoszenia problemu — a to
właśnie wtedy zgłoszenia są najbardziej potrzebne. Dane serwera poczty wpisuje
administrator w Ustawieniach aplikacji.

Publiczna marka (nazwa, kolor, ikona) też mieszka tutaj, bo powłoka aplikacji
i ekran logowania muszą ją odczytać PRZED zalogowaniem.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.auth import get_current_user
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Contact"])

MAX_TRESC = 5000


class ZgloszenieRequest(BaseModel):
    tresc: str


@router.get("/api/branding")
def get_branding(db: Session = Depends(get_db)):
    """Nazwa, kolor nazwy i ikona instancji. BEZ uwierzytelnienia — te same dane
    widać na ekranie logowania, a powłoka potrzebuje ich przy pierwszym renderze."""
    from app.settings.router import _cache_loaded, _load_cache_from_db, marka

    if not _cache_loaded:
        _load_cache_from_db(db)
    return marka()


@router.post("/api/contact")
def wyslij_zgloszenie(
    payload: ZgloszenieRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Wysyła zgłoszenie na adres wsparcia, z adresem zgłaszającego w „Reply-To".

    Bez skonfigurowanej poczty odpowiadamy 503 z jasną przyczyną — użytkownik ma
    wiedzieć, że wiadomość NIE poszła, zamiast zobaczyć potwierdzenie wysyłki,
    której nie było.
    """
    from app.settings.router import _cache_loaded, _load_cache_from_db, ustawienie

    if not _cache_loaded:
        _load_cache_from_db(db)

    tresc = (payload.tresc or "").strip()
    if len(tresc) < 10:
        raise HTTPException(status_code=400, detail="Opisz zgłoszenie w co najmniej 10 znakach.")
    if len(tresc) > MAX_TRESC:
        raise HTTPException(status_code=400, detail=f"Zgłoszenie może mieć najwyżej {MAX_TRESC} znaków.")

    host = ustawienie("smtp_host")
    odbiorca = ustawienie("support_email")
    nadawca = ustawienie("smtp_from") or ustawienie("smtp_user")
    if not (host and odbiorca and nadawca):
        raise HTTPException(
            status_code=503,
            detail="Wysyłka zgłoszeń nie jest skonfigurowana — uzupełnij dane poczty w Ustawieniach aplikacji.",
        )

    instancja = ustawienie("app_name") or "EDM"
    wiadomosc = EmailMessage()
    wiadomosc["Subject"] = f"[{instancja}] Zgłoszenie od {current_user.username}"
    wiadomosc["From"] = nadawca
    wiadomosc["To"] = odbiorca
    if current_user.email:
        # Odpowiedź ma trafić do zgłaszającego, a nie na skrzynkę techniczną.
        wiadomosc["Reply-To"] = current_user.email
    wiadomosc.set_content(
        f"Zgłaszający: {current_user.full_name or current_user.username}\n"
        f"Konto: {current_user.username} <{current_user.email}>\n"
        f"Instancja: {instancja}\n\n"
        f"{tresc}\n"
    )

    port = int(ustawienie("smtp_port", "587"))
    uzytkownik = ustawienie("smtp_user")
    haslo = ustawienie("smtp_password")
    try:
        # 465 to SMTPS (szyfrowanie od pierwszego bajtu), pozostałe porty
        # zaczynają jawnie i podnoszą szyfrowanie przez STARTTLS.
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as smtp:
                if uzytkownik:
                    smtp.login(uzytkownik, haslo)
                smtp.send_message(wiadomosc)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if uzytkownik:
                    smtp.login(uzytkownik, haslo)
                smtp.send_message(wiadomosc)
    except Exception as e:
        # Treści wyjątku nie pokazujemy użytkownikowi: potrafi zawierać adres
        # serwera i nazwę konta pocztowego.
        logger.error(f"[KONTAKT] Wysyłka zgłoszenia od {current_user.username} nieudana: {e}")
        raise HTTPException(
            status_code=502,
            detail="Nie udało się wysłać zgłoszenia. Administrator znajdzie powód w logu aplikacji.",
        )

    logger.info(f"[KONTAKT] Zgłoszenie od {current_user.username} wysłane na {odbiorca}")
    return {"wyslano": True, "do": odbiorca}
