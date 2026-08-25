"""Testy znaczników niezależnych od języka: cytowania `[[N]]` i odmowy `[[BRAK]]`.

Uruchom: pytest backend/tests/test_chat_jezyk_neutralny.py -v

Po co to powstało. Dwa mechanizmy były zaczepione o polskie słowa:

* cytowanie `[Źródło N]` — przy odpowiedzi po angielsku model przestawał je
  wystawiać, więc WSZYSTKIE źródła dostawały `cited: false` i chowały się pod zwijką;
* odmowa jako dosłowne polskie zdanie — zależały od niej CZTERY rzeczy: zdejmowanie
  doklejonego ogona, pomijanie tury w historii, ponowienie pytania „na czysto"
  w interfejsie i zerowanie źródeł w n8n. Odmowa po angielsku nie była rozpoznawana:
  trafiała do historii jak zwykła odpowiedź, razem ze źródłami, z których model
  nie skorzystał.

Obie postacie — nowa neutralna i stara polska — muszą działać RÓWNOLEGLE. Prompt w n8n
zmienia człowiek, więc wdrożenie kodu i „Publish" nie wypadają w tej samej minucie;
poza tym rozmowy zapisane wcześniej niosą postać starą i mają być czytelne na zawsze.
"""
import pytest

from app.chat.formulka import (FORMULKA, ZNACZNIK_BRAKU, FiltrKoncowejFormulki,
                               bez_koncowej_formulki, czy_odmowa)
from app.chat.router import _is_refusal, _strip_markers


def przepusc(tekst: str, rozmiar: int = 1) -> tuple[str, bool]:
    f = FiltrKoncowejFormulki()
    wynik = "".join(f.dodaj(tekst[i:i + rozmiar]) for i in range(0, len(tekst), rozmiar))
    return wynik + f.domknij(), f.usunieto


class TestZnacznikaCytowania:
    @pytest.mark.parametrize("tekst", [
        "Termin wynosi 7 dni [[1]].",
        "Termin wynosi 7 dni [Źródło 1].",
        "Dotyczy obu [[2, 5]].",
        "Dotyczy obu [Źródło 2, 5].",
        "Stary zapis [[Źródło 1]].",
    ])
    def test_obie_postacie_znikaja_z_historii(self, tekst):
        """Do historii dla modelu znaczniki nie idą — zaśmiecałyby prompt."""
        assert "[" not in _strip_markers(tekst)

    @pytest.mark.parametrize("tekst", [
        "Rozporządzenie z [2024] roku.",
        "Norma [ISO 9001] obowiązuje.",
        "Punkt [a] i [b].",
    ])
    def test_zwykly_nawias_w_tresci_zostaje(self, tekst):
        """Same cyfry liczą się jako cytowanie WYŁĄCZNIE w podwójnym nawiasie.
        Inaczej rok albo numer normy znikałby z odpowiedzi jako rzekome cytowanie."""
        assert _strip_markers(tekst) == tekst


class TestRozpoznaniaOdmowy:
    @pytest.mark.parametrize("tresc", [ZNACZNIK_BRAKU, FORMULKA,
                                       f"  {ZNACZNIK_BRAKU}  ", f"_adnotacja_\n{ZNACZNIK_BRAKU}"])
    def test_obie_postacie_to_odmowa(self, tresc):
        assert czy_odmowa(tresc.strip()) or _is_refusal(tresc)

    @pytest.mark.parametrize("tresc", [
        "Zwykła odpowiedź.",
        "Nie znaleziono terminu, ale procedura opisuje tryb zgłoszenia.",
        "[[BRAKUJE]]",
        "[[1]]",
    ])
    def test_co_odmowa_nie_jest(self, tresc):
        assert not _is_refusal(tresc)

    def test_odmowa_nie_wchodzi_do_historii(self):
        """Sedno: odmowa w pamięci modelu powoduje kolejne odmowy (zob. 0.5.4)."""
        assert _is_refusal(ZNACZNIK_BRAKU) is True


class TestStrumienia:
    def test_czysta_odmowa_dociera_w_calosci(self):
        """Znacznik jest CAŁĄ odpowiedzią — interfejs zamieni go na zdanie, więc
        musi dojść nietknięty."""
        wynik, usunieto = przepusc(ZNACZNIK_BRAKU)
        assert wynik == ZNACZNIK_BRAKU and usunieto is False

    def test_znacznik_doklejony_do_odpowiedzi_znika(self):
        """Model bywa połowiczny: odpowiada z treści, a „niepokrytą resztę" domyka
        odmową. Zmierzone 3 przebiegi na 5 — wygląda, jakby system sam sobie przeczył."""
        wynik, usunieto = przepusc(f"Termin wynosi 7 dni.\n{ZNACZNIK_BRAKU}")
        assert wynik.strip() == "Termin wynosi 7 dni." and usunieto is True

    def test_stara_formulka_doklejona_nadal_znika(self):
        wynik, usunieto = przepusc(f"Termin wynosi 7 dni.\n{FORMULKA}")
        assert wynik.strip() == "Termin wynosi 7 dni." and usunieto is True

    @pytest.mark.parametrize("rozmiar", [1, 2, 3, 5, 13])
    def test_niezaleznie_od_podzialu_strumienia(self, rozmiar):
        """Znacznik przychodzi w kawałkach po jednym tokenie — „[[", „BRA", „K]]"."""
        wynik, _ = przepusc(f"Odpowiedź.\n{ZNACZNIK_BRAKU}", rozmiar)
        assert wynik.strip() == "Odpowiedź."

    def test_tekst_zaczynajacy_sie_jak_znacznik_zostaje(self):
        """„[[1]]" na końcu to cytowanie, nie odmowa — nie wolno go zjeść."""
        wynik, usunieto = przepusc("Termin wynosi 7 dni [[1]]")
        assert wynik == "Termin wynosi 7 dni [[1]]" and usunieto is False

    def test_bez_koncowej_formulki_zdejmuje_obie_postacie(self):
        assert bez_koncowej_formulki(f"Treść.\n{ZNACZNIK_BRAKU}").strip() == "Treść."
        assert bez_koncowej_formulki(f"Treść.\n{FORMULKA}").strip() == "Treść."


class TestZnacznikaBezTrafien:
    """Komunikaty tworzone przez APLIKACJĘ (nie przez model): „nie znalazłem
    dokumentów spełniających kryteria", „nie wiem, o które dokumenty chodzi".

    Nie wolno ich wpuścić do historii dla modelu — odmowa w jego pamięci powoduje
    kolejne odmowy (zmierzone, 0.5.4). Rozpoznawaliśmy je po POCZĄTKU polskiego
    zdania, więc po przetłumaczeniu interfejsu przestałyby pasować i wróciłyby do
    historii. Znacznik `[[NOMATCH]]` jest identyczny w każdym języku.
    """

    @pytest.mark.parametrize("tresc", [
        "[[NOMATCH]]I found no documents matching the criteria.",
        "[[NOMATCH]]Nie znalazłem dokumentów spełniających kryteria (typ: Zarządzenie).",
        "[[NOMATCH]]Ich habe keine passenden Dokumente gefunden.",
    ])
    def test_znacznik_dziala_w_kazdym_jezyku(self, tresc):
        assert _is_refusal(tresc) is True

    @pytest.mark.parametrize("tresc", [
        "Nie znalazłem dokumentów spełniających kryteria (typ: Zarządzenie).",
        "_Nie znalazłem dokumentów spełniających kryteria_",
        "Nie wiem, o które dokumenty chodzi. Doprecyzuj — możesz podać rodzaj.",
        "W systemie nie ma rodzaju dokumentów o takiej nazwie.",
    ])
    def test_dawne_polskie_postacie_nadal_rozpoznane(self, tresc):
        """Rozmowy zapisane przed wprowadzeniem znacznika mają czytać się tak samo."""
        assert _is_refusal(tresc) is True

    @pytest.mark.parametrize("tresc", [
        "Znalazłem 3 dokumenty.",
        "Nie znaleziono terminu, ale procedura opisuje tryb zgłoszenia.",
        "I found 3 documents matching the criteria.",
    ])
    def test_zwykla_odpowiedz_wchodzi_do_historii(self, tresc):
        assert _is_refusal(tresc) is False
