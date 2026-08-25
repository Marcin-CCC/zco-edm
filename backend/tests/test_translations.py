"""Testy poprawek tłumaczeń interfejsu (zakładka „Języki").

Uruchom: pytest backend/tests/test_translations.py -v

Dwie rzeczy są tu naprawdę kruche i dlatego mają najwięcej przypadków:

1. **Odczyt odpowiedzi modelu.** Tłumaczymy partiami po 20 napisów i wiążemy wynik
   z wejściem po NUMERZE, nie po kolejności linii. Gdyby po kolejności, jedna zgubiona
   albo dołożona linia przesunęłaby całą resztę — a wtedy przycisk „Zapisz” dostałby
   tłumaczenie nagłówka kolumny i nikt by nie zauważył, bo oba są krótkie.

2. **Pusta wartość.** Znaczy „wróć do napisu z aplikacji”, więc musi KASOWAĆ wiersz.
   Zapisana jako pusty napis zostawiłaby w interfejsie puste miejsce zamiast
   polskiego zdania — i nie dałoby się jej odróżnić od świadomego tłumaczenia.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.translations.router import (
    ROZMIAR_PARTII,
    AutoIn,
    AutoItem,
    TranslationIn,
    _przetlumacz_partie,
    _sprawdz_jezyk,
    _tylko_admin,
    delete_override,
    machine_translate,
    read_overrides,
    upsert_override,
)


class Konto:
    def __init__(self, admin=True):
        self.id = 1
        self.username = "admin"
        self.is_admin = admin


class Zapytanie:
    """Najmniejsze udawane zapytanie SQLAlchemy: filtr, `first`, `all`, `delete`."""

    def __init__(self, baza):
        self.baza = baza

    def filter(self, *_warunki):
        return self

    def first(self):
        return self.baza.wiersze[0] if self.baza.wiersze else None

    def all(self):
        return list(self.baza.wiersze)

    def delete(self):
        ile = len(self.baza.wiersze)
        self.baza.wiersze = []
        self.baza.skasowane += ile
        return ile


class Baza:
    def __init__(self, wiersze=None):
        self.wiersze = wiersze or []
        self.dodane = []
        self.commity = 0
        self.skasowane = 0

    def query(self, *_modele):
        return Zapytanie(self)

    def add(self, obiekt):
        self.dodane.append(obiekt)
        self.wiersze.append(obiekt)

    def commit(self):
        self.commity += 1


class TestDostepu:
    def test_zwykly_uzytkownik_nie_zmienia_tlumaczen(self):
        with pytest.raises(HTTPException) as e:
            _tylko_admin(Konto(admin=False))
        assert e.value.status_code == 403

    def test_polskiego_nie_tlumaczy_sie_tutaj(self):
        """Polski jest źródłem — jego teksty zmienia się w kodzie. Dopuszczenie go
        tutaj dałoby dwa miejsca na tę samą prawdę."""
        with pytest.raises(HTTPException) as e:
            _sprawdz_jezyk("pl")
        assert e.value.status_code == 400

    @pytest.mark.parametrize("kod", ["fr", "klingoński", ""])
    def test_nieobslugiwany_jezyk_odrzucony(self, kod):
        with pytest.raises(HTTPException) as e:
            _sprawdz_jezyk(kod)
        assert e.value.status_code == 400

    def test_zapis_z_regionem_sprowadzony_do_jezyka(self):
        assert _sprawdz_jezyk("en-US") == "en"


class TestOdczytuDlaFrontu:
    def test_polski_nie_ma_poprawek(self):
        """Wywołanie idzie z serwera Next przy KAŻDYM renderze — dla języka bazowego
        ma wracać od razu, bez pytania bazy."""
        assert read_overrides("pl", db=None) == {}

    def test_nieznany_jezyk_nie_wywraca_strony(self):
        """Ciasteczko może nieść cokolwiek; pusty słownik zostawia napisy z katalogu.

        `db=None` jest tu SPRAWDZENIEM, nie skrótem: wyjście musi nastąpić przed
        dotknięciem bazy, bo to wywołanie idzie przy każdym renderze strony."""
        assert read_overrides("fr", db=None) == {}


class TestZapisu:
    def test_pusta_wartosc_kasuje_wiersz(self):
        baza = Baza(wiersze=[object()])
        wynik = upsert_override(
            TranslationIn(locale="en", key="shell.logout", value="   "),
            db=baza, current_user=Konto(),
        )
        assert baza.skasowane == 1 and baza.commity == 1
        assert wynik["value"] is None

    def test_nowa_wartosc_zapisuje_sie_jako_ludzka(self):
        baza = Baza()
        wynik = upsert_override(
            TranslationIn(locale="en", key="shell.logout", value="  Sign out  "),
            db=baza, current_user=Konto(),
        )
        assert wynik["value"] == "Sign out"           # obcięte białe znaki
        assert wynik["source"] == "human"
        assert baza.dodane and baza.dodane[0].source == "human"

    def test_pusty_klucz_odrzucony(self):
        with pytest.raises(HTTPException) as e:
            upsert_override(
                TranslationIn(locale="en", key="  ", value="cokolwiek"),
                db=Baza(), current_user=Konto(),
            )
        assert e.value.status_code == 400

    def test_kasowanie_wymaga_admina(self):
        with pytest.raises(HTTPException) as e:
            delete_override("en", "shell.logout", db=Baza(), current_user=Konto(admin=False))
        assert e.value.status_code == 403


def odpowiedz_modelu(tresc: str):
    """Podstawiony klient httpx zwracający jedną gotową odpowiedź vLLM."""

    class Odp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": tresc}}]}

    class Klient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, *_a, **_k):
            return Odp()

    return Klient


class TestOdczytuOdpowiedziModelu:
    @staticmethod
    def przetlumacz(monkeypatch, tresc, teksty):
        import app.translations.router as modul
        monkeypatch.setattr(modul.httpx, "AsyncClient", lambda *a, **k: odpowiedz_modelu(tresc)())
        return asyncio.run(_przetlumacz_partie("en", teksty))

    def test_zwykla_odpowiedz(self, monkeypatch):
        wynik = self.przetlumacz(monkeypatch, "1. Files\n2. Settings", ["Pliki", "Ustawienia"])
        assert wynik == ["Files", "Settings"]

    def test_kolejnosc_bierze_sie_z_numerow(self, monkeypatch):
        """Model bywa zamieniać linie miejscami. Numer wiąże tłumaczenie z napisem."""
        wynik = self.przetlumacz(monkeypatch, "2. Settings\n1. Files", ["Pliki", "Ustawienia"])
        assert wynik == ["Files", "Settings"]

    def test_zgubiona_linia_zostawia_dziure_a_nie_przesuwa(self, monkeypatch):
        """Sedno: brak drugiej linii NIE może wepchnąć trzeciego tłumaczenia na jej
        miejsce — wtedy dwa napisy naraz byłyby ciche i błędne."""
        wynik = self.przetlumacz(
            monkeypatch, "1. Files\n3. Users", ["Pliki", "Ustawienia", "Użytkownicy"])
        assert wynik == ["Files", "", "Users"]

    def test_wstep_i_puste_linie_ignorowane(self, monkeypatch):
        wynik = self.przetlumacz(
            monkeypatch,
            "Oto tłumaczenia:\n\n1. Files\n\n2. Settings\n\nMam nadzieję, że pomogłem.",
            ["Pliki", "Ustawienia"],
        )
        assert wynik == ["Files", "Settings"]

    def test_cudzyslowy_zdejmowane(self, monkeypatch):
        wynik = self.przetlumacz(monkeypatch, '1. "Files"', ["Pliki"])
        assert wynik == ["Files"]

    def test_numer_spoza_zakresu_nie_wywraca(self, monkeypatch):
        wynik = self.przetlumacz(monkeypatch, "1. Files\n9. Cokolwiek", ["Pliki"])
        assert wynik == ["Files"]

    def test_kropka_w_tlumaczeniu_nie_myli_odczytu(self, monkeypatch):
        """Dzielimy na PIERWSZEJ kropce, więc zdanie z kropkami ma zostać całe."""
        wynik = self.przetlumacz(
            monkeypatch, "1. No results. Try again.", ["Brak wyników. Spróbuj ponownie."])
        assert wynik == ["No results. Try again."]


class TestTlumaczeniaMaszynowego:
    def test_pusta_lista_nie_wola_modelu(self):
        wynik = asyncio.run(machine_translate(
            AutoIn(locale="en", items=[]), db=Baza(), current_user=Konto()))
        assert wynik == {"translated": {}, "failed": []}

    def test_awaria_modelu_nie_gubi_calosci(self, monkeypatch):
        """Nieudana partia ma wrócić jako `failed`, czyli zostać na liście braków —
        nie wolno jej zapisać jako pustego tłumaczenia."""
        import app.translations.router as modul

        async def wybuch(*_a, **_k):
            raise RuntimeError("model nie odpowiada")

        monkeypatch.setattr(modul, "_przetlumacz_partie", wybuch)
        baza = Baza()
        wynik = asyncio.run(machine_translate(
            AutoIn(locale="en", items=[AutoItem(key="a.b", source="Pliki")]),
            db=baza, current_user=Konto(),
        ))
        assert wynik["translated"] == {} and wynik["failed"] == ["a.b"]
        assert not baza.dodane

    def test_pominiety_napis_nie_zapisuje_sie_pusty(self, monkeypatch):
        import app.translations.router as modul

        async def polowicznie(_kod, teksty):
            return ["Files"] + [""] * (len(teksty) - 1)

        monkeypatch.setattr(modul, "_przetlumacz_partie", polowicznie)
        baza = Baza()
        wynik = asyncio.run(machine_translate(
            AutoIn(locale="en", items=[
                AutoItem(key="a.pliki", source="Pliki"),
                AutoItem(key="a.ustawienia", source="Ustawienia"),
            ]),
            db=baza, current_user=Konto(),
        ))
        assert wynik["translated"] == {"a.pliki": "Files"}
        assert wynik["failed"] == ["a.ustawienia"]

    def test_ograniczenie_liczby_napisow(self):
        with pytest.raises(HTTPException) as e:
            asyncio.run(machine_translate(
                AutoIn(locale="en", items=[AutoItem(key=f"k{i}", source="x") for i in range(501)]),
                db=Baza(), current_user=Konto(),
            ))
        assert e.value.status_code == 400

    def test_partie_sa_male(self):
        """Model gubi się przy długich listach; jedno żądanie na napis byłoby zbyt
        kosztowne. Wartość jest kompromisem i ma zostać pod kontrolą."""
        assert 5 <= ROZMIAR_PARTII <= 50
