"""Testy zdejmowania formułki doklejonej na końcu odpowiedzi.

Uruchom: pytest backend/tests/test_chat_formulka.py -v

Sedno tych testów to nie usuwanie (to jedna linijka), tylko PRZYPADKI GRANICZNE:
czysta odmowa musi przejść nietknięta, bo opiera się na niej ponowienie pytania po
zmianie tematu, pomijanie tury w historii i zerowanie źródeł w n8n.
"""
import json

from app.chat.formulka import FORMULKA, FiltrKoncowejFormulki, bez_koncowej_formulki


def przepusc(tekst: str, rozmiar: int = 1) -> tuple[str, bool]:
    """Przepuść tekst przez filtr kawałkami (domyślnie po znaku, jak tokeny modelu)."""
    f = FiltrKoncowejFormulki()
    wynik = "".join(f.dodaj(tekst[i:i + rozmiar]) for i in range(0, len(tekst), rozmiar))
    wynik += f.domknij()
    return wynik, f.usunieto


class TestCzystaOdmowaZostaje:
    """Odmowa jako CAŁA odpowiedź jest kontraktem — nie wolno jej ruszyć."""

    def test_sama_formulka_przechodzi_bez_zmian(self):
        wynik, usunieto = przepusc(FORMULKA)
        assert wynik == FORMULKA
        assert usunieto is False

    def test_formulka_z_bialymi_znakami_wokol(self):
        wynik, usunieto = przepusc(f"\n{FORMULKA}\n")
        assert wynik == f"\n{FORMULKA}\n"
        assert usunieto is False

    def test_niezaleznie_od_podzialu_na_kawalki(self):
        for rozmiar in (1, 3, 7, 64, 500):
            wynik, usunieto = przepusc(FORMULKA, rozmiar)
            assert wynik == FORMULKA, f"rozmiar kawałka {rozmiar}"
            assert usunieto is False


class TestDoklejkaZnika:
    def test_formulka_po_odpowiedzi(self):
        odpowiedz = "Delegacje reguluje Regulamin [Źródło 1]."
        wynik, usunieto = przepusc(f"{odpowiedz}\n\n{FORMULKA}")
        assert wynik.strip() == odpowiedz
        assert usunieto is True

    def test_formulka_zakonczona_nowa_linia(self):
        odpowiedz = "Zasady szkoleń opisuje Regulamin Pracy [Źródło 5]."
        wynik, usunieto = przepusc(f"{odpowiedz}\n\n{FORMULKA}\n")
        assert wynik.strip() == odpowiedz
        assert usunieto is True

    def test_dziala_przy_kazdym_podziale_strumienia(self):
        odpowiedz = "Krótka odpowiedź z treści dokumentów [Źródło 2]."
        for rozmiar in (1, 2, 5, 13, 100):
            wynik, usunieto = przepusc(f"{odpowiedz} {FORMULKA}", rozmiar)
            assert wynik.strip() == odpowiedz, f"rozmiar kawałka {rozmiar}"
            assert usunieto is True


class TestNicWiecejNieRuszamy:
    def test_zwykla_odpowiedz_bez_zmian(self):
        tekst = "Pracownik składa wniosek w terminie 3 dni roboczych [Źródło 1]."
        wynik, usunieto = przepusc(tekst)
        assert wynik == tekst
        assert usunieto is False

    def test_odpowiedz_konczaca_sie_litera_z_poczatku_formulki(self):
        """Ogon „N" jest początkiem formułki — musi ruszyć dalej na koniec strumienia."""
        tekst = "Dokument podpisał dyrektor N"
        wynik, usunieto = przepusc(tekst)
        assert wynik == tekst
        assert usunieto is False

    def test_formulka_w_srodku_odpowiedzi_zostaje(self):
        tekst = f"{FORMULKA} Natomiast w innych dokumentach znajduje się opis [Źródło 3]."
        wynik, usunieto = przepusc(tekst)
        assert wynik == tekst
        assert usunieto is False

    def test_zdanie_zaczynajace_sie_tak_samo_ale_dluzsze(self):
        tekst = "Odpowiedź. Niestety, nie znaleziono w dokumentach informacji na ten temat urlopu."
        wynik, usunieto = przepusc(tekst)
        assert wynik == tekst
        assert usunieto is False

    def test_pusty_strumien(self):
        wynik, usunieto = przepusc("")
        assert wynik == ""
        assert usunieto is False


class TestHistoriaRozmowy:
    """Stare odpowiedzi w bazie — ta sama zasada, tylko na gotowym tekście."""

    def test_zdejmuje_doklejke(self):
        assert bez_koncowej_formulki(f"Treść odpowiedzi.\n\n{FORMULKA}") == "Treść odpowiedzi."

    def test_zostawia_czysta_odmowe(self):
        assert bez_koncowej_formulki(FORMULKA) == FORMULKA

    def test_nie_rusza_zwyklej_odpowiedzi(self):
        tekst = "Wniosek składa się do Działu Personalnego."
        assert bez_koncowej_formulki(tekst) == tekst


class TestStrumienia:
    """Ten sam kod, który pracuje na produkcji: linie JSN n8n → bajty do przeglądarki."""

    @staticmethod
    def _strumien_n8n(kawalki: list[str], rozmiar_pakietu: int = 40) -> list[bytes]:
        """Bajty tak, jak przychodzą z n8n: linie JSON pocięte w losowych miejscach."""
        surowe = json.dumps({"type": "begin", "metadata": {}}).encode() + b"\n"
        for k in kawalki:
            surowe += json.dumps({"type": "item", "content": k, "metadata": {}},
                                 ensure_ascii=False).encode() + b"\n"
        surowe += json.dumps({"type": "end", "metadata": {}}).encode() + b"\n"
        return [surowe[i:i + rozmiar_pakietu] for i in range(0, len(surowe), rozmiar_pakietu)]

    @staticmethod
    def _odczytaj(wyjscie: bytes) -> tuple[str, list[str]]:
        """Odczyt jak we frontendzie: sklejony tekst + typy linii (kontrola ramek)."""
        tekst, typy = "", []
        for linia in wyjscie.decode().splitlines():
            if not linia.strip():
                continue
            obj = json.loads(linia)          # każda linia musi zostać poprawnym JSON-em
            typy.append(obj.get("type"))
            tekst += obj.get("content") or ""
        return tekst, typy

    def _przepusc(self, kawalki: list[str], rozmiar_pakietu: int = 40):
        import asyncio

        from app.chat.formulka import filtruj_strumien

        async def zrodlo():
            for p in self._strumien_n8n(kawalki, rozmiar_pakietu):
                yield p

        async def zbierz():
            return b"".join([c async for c in filtruj_strumien(zrodlo())])

        return self._odczytaj(asyncio.run(zbierz()))

    def test_doklejka_nie_dociera_do_odbiorcy(self):
        tekst, typy = self._przepusc(list("Odpowiedź z dokumentów. ") + [FORMULKA])
        assert tekst.strip() == "Odpowiedź z dokumentów."
        assert typy[0] == "begin" and typy[-1] == "end"     # ramki strumienia nietknięte

    def test_czysta_odmowa_dociera_w_calosci(self):
        tekst, _ = self._przepusc(list(FORMULKA))
        assert tekst == FORMULKA

    def test_zwykla_odpowiedz_przechodzi_bez_zmian(self):
        zdanie = "Pracownik składa wniosek w terminie 3 dni roboczych [Źródło 1]."
        tekst, _ = self._przepusc(list(zdanie))
        assert tekst == zdanie

    def test_niezaleznie_od_podzialu_bajtow(self):
        """Granice pakietów TCP wypadają w losowych miejscach, także w środku linii."""
        kawalki = list("Krótka odpowiedź. ") + [FORMULKA]
        for rozmiar in (1, 7, 40, 4096):
            tekst, typy = self._przepusc(kawalki, rozmiar)
            assert tekst.strip() == "Krótka odpowiedź.", f"pakiet {rozmiar}"
            assert typy[0] == "begin" and typy[-1] == "end", f"pakiet {rozmiar}"

    def test_linia_nie_bedaca_json_przechodzi_nietknieta(self):
        import asyncio

        from app.chat.formulka import filtruj_strumien

        async def zrodlo():
            yield b'data: [DONE]\n'

        async def zbierz():
            return b"".join([c async for c in filtruj_strumien(zrodlo())])

        assert asyncio.run(zbierz()) == b'data: [DONE]\n'
