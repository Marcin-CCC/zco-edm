"""Zdejmowanie formułki o braku informacji doklejonej NA KOŃCU prawdziwej odpowiedzi.

Model dostaje w prompcie n8n regułę „jeśli w Kontekście nie ma informacji, Twoja CAŁA
odpowiedź to dokładnie: «Niestety, nie znaleziono…»". Przy kontekście mieszanym (kilka
fragmentów na temat + reszta pustych formularzy) wykonuje ją POŁOWICZNIE: odpowiada z
części merytorycznej, a „niepokrytą resztę" domyka tym zdaniem. Zmierzone na pytaniu
„zasady szkoleń": 3 przebiegi na 5. Wygląda to tak, jakby system zaprzeczał sam sobie.

Prompt mówi wprost, żeby tego nie robić („pod ŻADNYM pozorem nie doklejaj"), więc
naprawa po stronie promptu byłaby powtórzeniem instrukcji, której model już nie
dotrzymuje. Zdejmujemy zdanie w locie, w przelocie strumienia przez backend.

CO ZOSTAJE NIETKNIĘTE (świadomie):

- Odpowiedź, której CAŁOŚĆ to ta formułka. To prawdziwa odmowa i wszystko, co po niej
  następuje, zależy od jej dosłownego brzmienia: ponowienie pytania „na czysto" po
  zmianie tematu (frontend), pominięcie tury w historii (`_is_refusal`) i wyzerowanie
  źródeł (węzeł Sources Gate w n8n).
- Formułka w ŚRODKU odpowiedzi — zdejmujemy wyłącznie ogon, bo tylko tam jest sprzeczna
  z resztą.
- Zdanie, które tylko zaczyna się tak samo, a biegnie dalej („…na ten temat urlopu.").

Filtr pracuje na strumieniu tokenów, więc formułka przychodzi w kawałkach. Wstrzymujemy
najkrótszy możliwy ogon: tekst wysyłamy dalej natychmiast, oprócz końcówki, która JEST
początkiem formułki. Taka końcówka rusza dalej przy pierwszym znaku, który do formułki
nie pasuje, albo na koniec strumienia — jeśli nie okazała się doklejonym zdaniem.
"""

import json
import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

FORMULKA = "Niestety, nie znaleziono w dokumentach informacji na ten temat."

# Zapas na białe znaki za kropką: model kończy zwykle „…temat.\n". Ogon musi je objąć,
# inaczej sam znak nowej linii zerwałby dopasowanie i formułka poszłaby dalej.
_ZAPAS_BIALYCH = 8


def _ogon(bufor: str) -> str:
    """Najdłuższa końcówka `bufor`, która jest początkiem formułki (albo nią całą).

    Zwraca "" gdy końcówka nie zapowiada formułki — wtedy cały bufor idzie dalej.
    """
    n = len(bufor)
    for k in range(min(n, len(FORMULKA) + _ZAPAS_BIALYCH), 0, -1):
        s = bufor[n - k:]
        if FORMULKA.startswith(s):
            return s                                    # niepełny początek
        if s.startswith(FORMULKA) and not s[len(FORMULKA):].strip():
            return s                                    # pełna formułka + białe znaki
    return ""


class FiltrKoncowejFormulki:
    """Przepuszcza tekst odpowiedzi, wstrzymując ewentualną formułkę na końcu.

    Użycie: `dodaj()` dla każdego kawałka strumienia, `domknij()` na jego koniec.
    """

    def __init__(self) -> None:
        self._zawieszone = ""
        self._byla_tresc = False
        self.usunieto = False

    def dodaj(self, tekst: str) -> str:
        """Zwróć tekst do wysłania dalej (może być pusty, gdy wszystko wstrzymane)."""
        if not tekst:
            return ""
        bufor = self._zawieszone + tekst
        self._zawieszone = _ogon(bufor)
        do_wyslania = bufor[: len(bufor) - len(self._zawieszone)]
        if do_wyslania.strip():
            self._byla_tresc = True
        return do_wyslania

    def domknij(self) -> str:
        """Zamknij odpowiedź: zwróć wstrzymany ogon albo "" , jeśli to doklejka."""
        ogon, self._zawieszone = self._zawieszone, ""
        if self._byla_tresc and ogon.strip() == FORMULKA:
            self.usunieto = True
            return ""
        if ogon.strip():
            self._byla_tresc = True
        return ogon


def _linia_tekstu(tekst: str) -> bytes:
    """Kawałek tekstu w formacie strumienia n8n (linia JSON typu „item")."""
    return json.dumps({"type": "item", "content": tekst}, ensure_ascii=False).encode() + b"\n"


async def filtruj_strumien(zrodlo, opis: str = "") -> AsyncIterator[bytes]:
    """Przepuść strumień odpowiedzi z n8n, zdejmując formułkę doklejoną na końcu.

    Strumień to linie JSON — `{"type":"item","content":"…"}` przeplatane begin/end/error.
    Ruszamy WYŁĄCZNIE pole z tekstem; linii, których nie rozumiemy, nie tykamy wcale.
    Podział na kawałki bajtów jest przypadkowy, więc linie sklejamy z bufora.
    """
    filtr = FiltrKoncowejFormulki()
    resztka = b""

    def linia_wyjscia(surowa: bytes) -> bytes:
        if not surowa.strip():
            return surowa + b"\n"
        try:
            obj = json.loads(surowa)
        except (ValueError, UnicodeDecodeError):
            return surowa + b"\n"
        if not isinstance(obj, dict):
            return surowa + b"\n"
        # Kolejność kluczy jak przy odczycie po stronie frontendu (extractFromParsed)
        klucz = next((k for k in ("content", "text", "output", "chunk", "message")
                      if isinstance(obj.get(k), str)), None)
        if klucz is None:
            # begin/end/error albo linia ze źródłami — wypowiedź modelu się skończyła,
            # więc wstrzymany ogon musi ruszyć TERAZ, przed tą linią.
            ogon = filtr.domknij()
            return (_linia_tekstu(ogon) if ogon else b"") + surowa + b"\n"
        obj[klucz] = filtr.dodaj(obj[klucz])
        return json.dumps(obj, ensure_ascii=False).encode() + b"\n"

    try:
        async for kawalek in zrodlo:
            resztka += kawalek
            if b"\n" not in resztka:
                continue
            czesci = resztka.split(b"\n")
            resztka = czesci.pop()
            wyjscie = b"".join(linia_wyjscia(l) for l in czesci)
            if wyjscie:
                yield wyjscie
    except httpx.HTTPError as e:
        logger.error(f"[CHAT] Przerwany strumień z n8n{opis}: {e}")
        resztka = b""
    if resztka:
        yield linia_wyjscia(resztka)
    ogon = filtr.domknij()          # tekst wstrzymany, gdy strumień urwał się bez „end"
    if ogon:
        yield _linia_tekstu(ogon)
    if filtr.usunieto:
        logger.info(f"[CHAT] Zdjęto formułkę doklejoną do odpowiedzi{opis}")


def bez_koncowej_formulki(tekst: str) -> str:
    """To samo dla gotowego tekstu (historia rozmowy zapisana przed tą poprawką).

    Stare odpowiedzi w bazie mają formułkę doklejoną i wracają do modelu jako historia,
    a wzorzec z historii sam zachęca do powtórki.
    """
    obciety = (tekst or "").rstrip()
    if not obciety.endswith(FORMULKA):
        return tekst
    reszta = obciety[: -len(FORMULKA)]
    return reszta.rstrip() if reszta.strip() else tekst
