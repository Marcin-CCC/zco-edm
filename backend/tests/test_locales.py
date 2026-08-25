"""Testy języka interfejsu zapisywanego przy koncie.

Uruchom: pytest backend/tests/test_locales.py -v

Kolumna `users.locale` steruje tym, który katalog tłumaczeń dostaje przeglądarka.
Wpis, dla którego katalogu nie ma, zostawiłby użytkownika z interfejsem bez tekstów —
dlatego wartości spoza listy nie wolno zapisać, a nie tylko „nie należy".

Pusty napis znaczy „wróć do domyślnego wdrożenia" i MUSI trafić do bazy jako NULL:
gdyby zapisał się jako "", kolumna przestałaby odróżniać brak wyboru od wyboru.
"""
import asyncio
import os

import pytest
from fastapi import HTTPException

from app.auth.auth import update_own_profile
from app.locales import BASE_LOCALE, SUPPORTED_LOCALES, default_locale, normalize_locale
from app.schema_upgrade import NEW_COLUMNS
from app.schemas import ProfileUpdate


class Konto:
    """Najmniejszy zamiennik użytkownika — endpoint dotyka tylko tych pól."""

    def __init__(self, locale=None):
        self.username = "tester"
        self.email = "tester@example.com"
        self.full_name = "Test Owy"
        self.locale = locale


class Baza:
    """Zamiennik sesji; liczy zapisy, bo cichy brak commitu byłby tu niewidoczny."""

    def __init__(self):
        self.commity = 0

    def commit(self):
        self.commity += 1

    def refresh(self, _obiekt):
        pass


def zmien(konto, wartosc):
    baza = Baza()
    asyncio.run(update_own_profile(ProfileUpdate(locale=wartosc), current_user=konto, db=baza))
    return baza.commity


class TestNormalizacji:
    @pytest.mark.parametrize("wejscie,wynik", [
        ("pl", "pl"),
        ("en", "en"),
        ("EN", "en"),          # przeglądarki podają wielkimi
        ("en-US", "en"),       # z regionem
        ("en_GB", "en"),       # zapis z podkreśleniem
        ("  pl  ", "pl"),
    ])
    def test_rozpoznane_postacie(self, wejscie, wynik):
        assert normalize_locale(wejscie) == wynik

    # „fr" nie jest na liście — gdyby kiedyś doszedł, ten test wskaże miejsce
    # do zmiany zamiast po cichu przestać cokolwiek sprawdzać.
    @pytest.mark.parametrize("wejscie", ["fr", "polski", "", None, "xx-YY"])
    def test_nierozpoznane_daja_none(self, wejscie):
        assert "fr" not in SUPPORTED_LOCALES, "zmień przykład — francuski doszedł do listy"
        assert normalize_locale(wejscie) is None

    def test_polski_jest_bazowy_i_obslugiwany(self):
        assert BASE_LOCALE == "pl" and BASE_LOCALE in SUPPORTED_LOCALES

    def test_domyslny_ze_srodowiska(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_LOCALE", "en")
        assert default_locale() == "en"

    def test_bledna_wartosc_srodowiska_nie_wywraca_startu(self, monkeypatch):
        """Literówka we wdrożeniu ma dać polski, a nie pusty interfejs."""
        monkeypatch.setenv("DEFAULT_LOCALE", "klingoński")
        assert default_locale() == BASE_LOCALE


class TestZapisuPrzyKoncie:
    def test_wybor_zapisuje_sie(self):
        konto = Konto()
        assert zmien(konto, "en") == 1
        assert konto.locale == "en"

    def test_pusty_napis_wraca_do_domyslnego_wdrozenia(self):
        """NULL, nie "" — inaczej kolumna przestaje odróżniać brak wyboru od wyboru."""
        konto = Konto(locale="en")
        assert zmien(konto, "") == 1
        assert konto.locale is None

    def test_nieobslugiwany_jezyk_odrzucony(self):
        konto = Konto(locale="pl")
        with pytest.raises(HTTPException) as e:
            zmien(konto, "fr")
        assert e.value.status_code == 400
        assert konto.locale == "pl"          # nic nie ruszone

    def test_ten_sam_jezyk_nie_powoduje_zapisu(self):
        konto = Konto(locale="en")
        assert zmien(konto, "en") == 0

    def test_brak_pola_nie_kasuje_wyboru(self):
        """Zapis samego imienia na stronie Profil nie może zdjąć języka."""
        konto = Konto(locale="en")
        baza = Baza()
        asyncio.run(update_own_profile(
            ProfileUpdate(full_name="Test Owy"), current_user=konto, db=baza))
        assert konto.locale == "en"


class TestSchematu:
    def test_kolumna_jest_dokladana_a_nie_wymagana(self):
        """Kolumna musi wchodzić przez uaktualnienia schematu i być NULL-owalna —
        bez tego powrót do starszego obrazu wymagałby ruszania bazy."""
        wpis = [k for k in NEW_COLUMNS if k[0] == "users" and k[1] == "locale"]
        assert wpis, "brak users.locale w NEW_COLUMNS"
        assert "NOT NULL" not in wpis[0][2].upper()


class TestKatalogowTlumaczen:
    """Pilnowanie katalogów `frontend/messages/*.json`.

    Front nie ma własnego uruchamiacza testów, a to jedyny zestaw idący w CI.

    **Dlaczego kompletności wymagamy tylko od angielskiego.** Napisy powstają po
    polsku, a angielski jest językiem, w którym system się pokazuje — te dwa muszą
    się zgadzać co do jednego klucza. Pozostałe języki dochodzą stopniowo: napis bez
    tłumaczenia wypada po polsku (katalog jest DOKŁADANY na bazowy), a uzupełnia się
    go w zakładce „Języki”, bez wydawania nowej wersji. Wymóg kompletności dla nich
    znaczyłby, że każdy nowy przycisk trzeba przetłumaczyć na pięć języków, zanim
    w ogóle da się go wdrożyć — a to zablokowałoby rozwój, nie poprawiło tłumaczeń.

    Klucza SPOZA katalogu bazowego nie wolno mieć nigdy i w żadnym języku: to zawsze
    literówka, a napis pod nim nigdy się nie pokaże, więc nikt by jej nie zauważył.
    """

    @staticmethod
    def katalog(kod: str) -> dict:
        import json
        from pathlib import Path

        sciezka = Path(__file__).resolve().parents[2] / "frontend" / "messages" / f"{kod}.json"
        assert sciezka.exists(), f"brak katalogu tłumaczeń: {sciezka}"
        return json.loads(sciezka.read_text(encoding="utf-8"))

    @staticmethod
    def klucze(d: dict, przedrostek: str = "") -> set[str]:
        wynik: set[str] = set()
        for k, v in d.items():
            pelny = f"{przedrostek}{k}"
            wynik |= TestKatalogowTlumaczen.klucze(v, f"{pelny}.") if isinstance(v, dict) else {pelny}
        return wynik

    @pytest.mark.parametrize("kod", SUPPORTED_LOCALES)
    def test_kazdy_jezyk_ma_swoj_katalog(self, kod):
        """Brak pliku to nie „język bez tłumaczeń", tylko wyjątek przy renderowaniu
        strony — `import` katalogu leci przy każdym żądaniu."""
        assert self.katalog(kod), f"pusty katalog dla {kod}"

    @pytest.mark.parametrize("kod", [k for k in SUPPORTED_LOCALES if k != BASE_LOCALE])
    def test_bez_kluczy_spoza_polskiego(self, kod):
        nadmiarowe = self.klucze(self.katalog(kod)) - self.klucze(self.katalog(BASE_LOCALE))
        assert not nadmiarowe, f"{kod}.json: klucze spoza katalogu bazowego: {sorted(nadmiarowe)}"

    def test_angielski_kompletny(self):
        """Twardy wymóg — angielskim system się pokazuje i nie może w nim wypaść
        polskie zdanie w środku ekranu."""
        brakujace = self.klucze(self.katalog(BASE_LOCALE)) - self.klucze(self.katalog("en"))
        assert not brakujace, f"en.json: brakuje tłumaczeń: {sorted(brakujace)}"

    def test_pokrycie_pozostalych_jezykow(self, capsys):
        """Nie przewraca budowy — wypisuje stan, żeby ubytek był widoczny w CI.
        Uzupełnianie odbywa się w zakładce „Języki”, nie przy wydaniu."""
        wszystkie = self.klucze(self.katalog(BASE_LOCALE))
        with capsys.disabled():
            print("\n  pokrycie katalogów w obrazie (reszta dochodzi w zakładce Języki):")
            for kod in SUPPORTED_LOCALES:
                if kod == BASE_LOCALE:
                    continue
                mam = len(self.klucze(self.katalog(kod)) & wszystkie)
                print(f"    {kod}: {mam}/{len(wszystkie)}")
        assert wszystkie, "katalog bazowy jest pusty"
