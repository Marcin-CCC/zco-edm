"""Identyfikacja instancji: ikona, nazwa i kolor nazwy.

Do wersji 1.2.0 marka pochodziła ze zmiennych środowiskowych ustawianych przy
wdrożeniu — w TRZECH miejscach naraz (CI oraz pliki compose obu instancji).
Raz się to zemściło: ZCO pokazało ikonę HiRS, bo zmienna trafiła do jednego
miejsca zamiast trzech. Od layoutu 1.5 wartości mieszkają w bazie i zmienia je
administrator z ekranu Ustawienia aplikacji.

Zmienne środowiskowe zostają jako WARTOŚĆ POCZĄTKOWA i awaryjna: świeża instancja
nadal wstaje z własną nazwą i kolorem, a gdyby ustawienia w bazie były puste,
aplikacja wygląda jak dotąd. Nazwa ze zmiennej `APP_NAME` pełni przy tym drugą
rolę — rozróżnia instancje w raportach e-mail z parsowania (`[ZCO DM]`, `[HiRS]`)
— więc jej NIE nadpisujemy w środowisku, tylko czytamy obok.

Ikona trafia do bazy jako data URI, nie na dysk. Powód jest praktyczny: katalog
dokumentów to zamontowany wolumen z plikami klienta, a zakładanie drugiego
wolumenu wyłącznie na jeden plik ikony byłoby kosztem większym niż zysk.
"""
import base64
import re
import struct

from fastapi import HTTPException, UploadFile
from app.messages import UserMessage

MAX_ICON_BYTES = 512 * 1024
DOZWOLONE_TYPY = {"png": "image/png", "svg": "image/svg+xml"}

# Kolor nazwy podajemy w zapisie szesnastkowym — tak jak w makiecie.
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def wymiary_png(dane: bytes) -> tuple[int, int] | None:
    """Szerokość i wysokość PNG-a z nagłówka IHDR.

    Czytamy 8 bajtów spod stałego offsetu zamiast wciągać bibliotekę do obrazów:
    do sprawdzenia proporcji 1:1 nie trzeba dekodować pikseli.
    """
    if len(dane) < 24 or dane[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    szerokosc, wysokosc = struct.unpack(">II", dane[16:24])
    return szerokosc, wysokosc


def wymiary_svg(tekst: str) -> tuple[float, float] | None:
    """Proporcje SVG — najpierw z `viewBox`, potem z `width`/`height`."""
    m = re.search(r'viewBox\s*=\s*["\']\s*[\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)', tekst)
    if m:
        return float(m.group(1)), float(m.group(2))
    w = re.search(r'\bwidth\s*=\s*["\']([\d.]+)', tekst)
    h = re.search(r'\bheight\s*=\s*["\']([\d.]+)', tekst)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    return None


async def wczytaj_ikone(plik: UploadFile) -> str:
    """Sprawdza format i proporcje, zwraca ikonę jako data URI.

    Kwadratowość jest wymagana, bo ikona pojawia się w polu 36×36 px także
    w zwiniętym menu — prostokąt zostałby tam ściśnięty i wyglądałby na błąd
    aplikacji, a nie na źle dobrany plik.
    """
    nazwa = (plik.filename or "").lower()
    rozszerzenie = nazwa.rsplit(".", 1)[-1] if "." in nazwa else ""
    if rozszerzenie not in DOZWOLONE_TYPY:
        raise HTTPException(status_code=400, detail=UserMessage("branding.iconType"))

    dane = await plik.read()
    if not dane:
        raise HTTPException(status_code=400, detail=UserMessage("files.empty"))
    if len(dane) > MAX_ICON_BYTES:
        raise HTTPException(
            status_code=400,
            detail=UserMessage("branding.iconTooBig", limit=MAX_ICON_BYTES // 1024),
        )

    if rozszerzenie == "png":
        wymiary = wymiary_png(dane)
        if wymiary is None:
            raise HTTPException(status_code=400, detail=UserMessage("branding.notPng"))
        szerokosc, wysokosc = wymiary
        if szerokosc != wysokosc:
            raise HTTPException(
                status_code=400,
                detail=UserMessage("branding.iconNotSquare", wymiary=f"{szerokosc}×{wysokosc} px"),
            )
        if szerokosc < 64:
            raise HTTPException(status_code=400, detail=UserMessage("branding.iconTooSmall"))
    else:
        tekst = dane.decode("utf-8", errors="ignore")
        if "<svg" not in tekst.lower():
            raise HTTPException(status_code=400, detail=UserMessage("branding.notSvg"))
        wymiary = wymiary_svg(tekst)
        if wymiary and abs(wymiary[0] - wymiary[1]) > 0.5:
            raise HTTPException(
                status_code=400,
                detail=UserMessage("branding.iconNotSquare", wymiary=f"{wymiary[0]:g}×{wymiary[1]:g}"),
            )

    return f"data:{DOZWOLONE_TYPY[rozszerzenie]};base64,{base64.b64encode(dane).decode('ascii')}"


def sprawdz_kolor(wartosc: str) -> str:
    """Kolor nazwy w zapisie szesnastkowym; inne zapisy odrzucamy."""
    kolor = (wartosc or "").strip()
    if not HEX_RE.match(kolor):
        raise HTTPException(status_code=400, detail=UserMessage("settings.badColor"))
    return kolor.lower()
