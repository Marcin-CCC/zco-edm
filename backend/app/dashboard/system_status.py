"""Stan serwera pod panele „Status systemu" i „Miejsce w systemie" na Dashboardzie.

Skąd biorą się te liczby — bo nie jest to oczywiste:

* **Obciążenie i pamięć** czytamy z `/proc`. Kontener dzieli jądro z hostem, więc
  `/proc/loadavg` i `/proc/meminfo` pokazują cały serwer, nie sam kontener. To
  jest zamierzone: interesuje nas, czy Spark jest zajęty, a nie ile zżera backend.
* **GPU** — świadomie NIE mierzymy procentu użycia. W obrazie backendu nie ma
  `nvidia-smi`, a dokładanie go wymagałoby przebudowy obrazu z runtime NVIDIA
  i podniesienia uprawnień kontenera. Zamiast tego pytamy vLLM o długość kolejki
  (`num_requests_running` / `num_requests_waiting`): odpowiada to na pytanie
  „czy model jest teraz zajęty" celniej niż chwilowy odczyt GPU, który skacze
  między 0 a 100 w ciągu sekundy.
* **Dysk** to CAŁY wolumen, na którym leży katalog dokumentów — dzielony na
  Sparku z modelami, obrazami Dockera i n8n. Dlatego obok procentu podajemy
  osobno rozmiar samych dokumentów: bez tego ktoś zobaczy kiedyś 80% i wywoła
  alarm o dokumentach, gdy naprawdę urosły modele.

Odczyt jest w pamięci podręcznej na ``TTL``, żeby wejście na Dashboard nie
strzelało do vLLM i Doclinga przy każdym renderze.
"""
import logging
import os
import shutil
import time

import httpx
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import File

logger = logging.getLogger(__name__)

# Świeżość odczytu. Piętnaście sekund wystarcza, żeby panel nie kłamał, a
# jednocześnie kilka osób odświeżających Dashboard nie robi z tego ruchu.
TTL = 15.0
# Usługi zewnętrzne odpytujemy krótko: panel informacyjny nie może blokować
# ładowania całego ekranu, gdy Spark akurat nie odpowiada.
TIMEOUT = 2.0

_cache: dict | None = None
_cache_ts = 0.0


def _load() -> tuple[float, int] | None:
    """Średnie obciążenie z ostatniej minuty i liczba rdzeni — albo None poza Linuksem."""
    try:
        with open("/proc/loadavg") as f:
            minuta = float(f.read().split()[0])
        return minuta, os.cpu_count() or 1
    except (OSError, ValueError, IndexError):
        return None


def _pamiec() -> tuple[int, int] | None:
    """(zajęte, całość) w bajtach. Liczymy z `MemAvailable`, nie z `MemFree` —
    pamięć oddana na bufory dyskowe jest do odzyskania i nie jest „zajęta"."""
    try:
        wartosci = {}
        with open("/proc/meminfo") as f:
            for linia in f:
                klucz, _, reszta = linia.partition(":")
                if klucz in ("MemTotal", "MemAvailable"):
                    wartosci[klucz] = int(reszta.split()[0]) * 1024
        if "MemTotal" not in wartosci or "MemAvailable" not in wartosci:
            return None
        return wartosci["MemTotal"] - wartosci["MemAvailable"], wartosci["MemTotal"]
    except (OSError, ValueError, IndexError):
        return None


def _istniejacy_przodek(sciezka: str) -> str:
    """Najbliższy istniejący katalog nadrzędny — albo korzeń.

    Katalog dokumentów potrafi jeszcze nie istnieć (świeża instancja przed
    pierwszym wgraniem pliku). Wolumen, na którym POWSTANIE, jest ten sam co
    jego katalogu nadrzędnego, więc odczyt zajętości jest wtedy nadal prawdziwy.
    """
    biezaca = os.path.abspath(sciezka or os.sep)
    while not os.path.isdir(biezaca):
        rodzic = os.path.dirname(biezaca)
        if rodzic == biezaca:
            return os.sep
        biezaca = rodzic
    return biezaca


def _dysk(db: Session) -> dict:
    """Zajętość wolumenu z dokumentami plus udział samych dokumentów.

    Rozmiar dokumentów bierzemy z bazy, a nie z obchodzenia katalogu: przy
    kilku tysiącach plików `os.walk` przy każdym wejściu na Dashboard kosztowałby
    więcej niż cała reszta tego endpointu.
    """
    wynik: dict = {"dostepny": False}
    try:
        uzycie = shutil.disk_usage(_istniejacy_przodek(settings.STORAGE_PATH))
        wynik = {
            "dostepny": True,
            "total": uzycie.total,
            "used": uzycie.used,
            "free": uzycie.free,
            "percent": round(uzycie.used / uzycie.total * 100, 1) if uzycie.total else 0.0,
        }
    except OSError as e:
        logger.warning(f"[STATUS] Nie udało się odczytać zajętości dysku: {e}")

    wynik["documents_bytes"] = int(db.query(func.coalesce(func.sum(File.size), 0)).scalar() or 0)
    return wynik


def _baza(db: Session) -> dict:
    """Czas odpowiedzi bazy. Jedno `SELECT 1` — mierzymy drogę, nie zapytanie."""
    start = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        return {"online": True, "ms": round((time.monotonic() - start) * 1000, 1)}
    except Exception as e:  # noqa: BLE001 — awaria bazy ma dać status, nie wyjątek
        logger.warning(f"[STATUS] Baza danych nie odpowiada: {e}")
        return {"online": False, "ms": None}


def _metryka(tekst: str, nazwa: str) -> float | None:
    """Wartość metryki Prometheusa z odpowiedzi `/metrics`.

    vLLM opatruje metryki etykietą modelu (`vllm:num_requests_running{model=...}`),
    więc nie da się porównać całej linii. Sam przedrostek też nie wystarcza:
    złapałby metrykę o dłuższej nazwie zaczynającej się tak samo (`..._total`),
    czyli licznik od startu usługi zamiast bieżącej kolejki. Stąd warunek na
    znak PO nazwie: klamra etykiet albo spacja przed wartością.
    """
    for linia in tekst.splitlines():
        if not linia.startswith(nazwa):
            continue
        if linia[len(nazwa):len(nazwa) + 1] not in ("{", " "):
            continue
        try:
            return float(linia.rsplit(" ", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


def _vllm() -> dict:
    """Model językowy: czy odpowiada i ile zapytań ma na głowie."""
    try:
        with httpx.Client(timeout=TIMEOUT) as klient:
            odp = klient.get(f"{settings.VLLM_URL.rstrip('/')}/metrics")
            odp.raise_for_status()
        tekst = odp.text
        liczy = _metryka(tekst, "vllm:num_requests_running")
        czeka = _metryka(tekst, "vllm:num_requests_waiting")
        return {
            "online": True,
            "running": int(liczy) if liczy is not None else None,
            "waiting": int(czeka) if czeka is not None else None,
        }
    except Exception as e:  # noqa: BLE001
        logger.info(f"[STATUS] vLLM nie odpowiada: {e}")
        return {"online": False, "running": None, "waiting": None}


def _docling() -> dict:
    """Usługa zamiany dokumentów na tekst."""
    try:
        with httpx.Client(timeout=TIMEOUT) as klient:
            odp = klient.get(f"{settings.DOCLING_API_URL.rstrip('/')}/health")
        return {"online": odp.status_code < 500}
    except Exception as e:  # noqa: BLE001
        logger.info(f"[STATUS] Docling nie odpowiada: {e}")
        return {"online": False}


def zbierz(db: Session) -> dict:
    """Pełny odczyt stanu — z pamięcią podręczną na ``TTL`` sekund."""
    global _cache, _cache_ts
    if _cache is not None and time.monotonic() - _cache_ts < TTL:
        return _cache

    obciazenie = _load()
    pamiec = _pamiec()
    docling = _docling()
    vllm = _vllm()

    _cache = {
        "aplikacja": {
            "online": True,
            "load": round(obciazenie[0], 2) if obciazenie else None,
            "cores": obciazenie[1] if obciazenie else None,
            # Obciążenie jako procent mocy serwera — samo „0.33" nic nie mówi
            # bez wiedzy, ile jest rdzeni.
            "load_percent": round(obciazenie[0] / obciazenie[1] * 100, 1) if obciazenie else None,
            "memory_used": pamiec[0] if pamiec else None,
            "memory_total": pamiec[1] if pamiec else None,
        },
        "baza": _baza(db),
        # Parser to para usług: Docling wyciąga tekst, vLLM rozumie treść.
        # Awaria którejkolwiek zatrzymuje przetwarzanie, więc status jest wspólny.
        "parser": {
            "online": docling["online"] and vllm["online"],
            "docling": docling["online"],
            "model": vllm["online"],
            "running": vllm["running"],
            "waiting": vllm["waiting"],
        },
        "magazyn": _dysk(db),
    }
    _cache_ts = time.monotonic()
    return _cache


def wyczysc_cache() -> None:
    """Kasuje pamięć podręczną — dla testów, żeby jeden nie zatruwał drugiego."""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0
