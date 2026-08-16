"""Testy walidacji ikony aplikacji i koloru nazwy.

Uruchom: pytest backend/tests/test_branding.py -v

Ikona trafia do pola 36×36 px także w zwiniętym menu, więc prostokąt zostałby tam
ściśnięty i wyglądałby na błąd aplikacji. Sprawdzenie proporcji jest tu jedyną
rzeczą, która to powstrzymuje — i dlatego ma testy.
"""
import asyncio
import base64
import io
import struct

import pytest
from fastapi import HTTPException, UploadFile

from app.branding import sprawdz_kolor, wczytaj_ikone, wymiary_png, wymiary_svg


def png(szerokosc: int, wysokosc: int) -> bytes:
    """Najkrótszy bajtowo poprawny nagłówek PNG o zadanych wymiarach."""
    ihdr = struct.pack(">II", szerokosc, wysokosc) + b"\x08\x06\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + ihdr + b"\x00" * 4


def plik(nazwa: str, dane: bytes) -> UploadFile:
    return UploadFile(filename=nazwa, file=io.BytesIO(dane))


class TestWymiary:
    def test_png_czyta_naglowek(self):
        assert wymiary_png(png(128, 128)) == (128, 128)

    def test_nie_png_daje_none(self):
        assert wymiary_png(b"to nie jest png") is None

    @pytest.mark.parametrize("svg,oczekiwane", [
        ('<svg viewBox="0 0 64 64"></svg>', (64.0, 64.0)),
        ('<svg width="48" height="24"></svg>', (48.0, 24.0)),
        ('<svg viewBox="0 0 10 20" width="99" height="99"></svg>', (10.0, 20.0)),  # viewBox wygrywa
    ])
    def test_svg(self, svg, oczekiwane):
        assert wymiary_svg(svg) == oczekiwane

    def test_svg_bez_wymiarow(self):
        assert wymiary_svg("<svg></svg>") is None


class TestWczytajIkone:
    def test_kwadratowy_png_przechodzi(self):
        wynik = asyncio.run(wczytaj_ikone(plik("logo.png", png(256, 256))))
        assert wynik.startswith("data:image/png;base64,")
        assert base64.b64decode(wynik.split(",", 1)[1])[:8] == b"\x89PNG\r\n\x1a\n"

    def test_prostokat_odrzucony_z_wymiarami_w_komunikacie(self):
        with pytest.raises(HTTPException) as e:
            asyncio.run(wczytaj_ikone(plik("logo.png", png(256, 128))))
        assert e.value.status_code == 400
        assert "256×128" in e.value.detail

    def test_za_mala_ikona(self):
        with pytest.raises(HTTPException) as e:
            asyncio.run(wczytaj_ikone(plik("logo.png", png(32, 32))))
        assert "za mała" in e.value.detail

    def test_svg_kwadratowy(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64"/></svg>'
        assert asyncio.run(wczytaj_ikone(plik("logo.svg", svg))).startswith("data:image/svg+xml;base64,")

    def test_svg_prostokatny_odrzucony(self):
        svg = b'<svg viewBox="0 0 120 40"></svg>'
        with pytest.raises(HTTPException):
            asyncio.run(wczytaj_ikone(plik("logo.svg", svg)))

    @pytest.mark.parametrize("nazwa", ["logo.jpg", "logo.gif", "logo.ico", "logo"])
    def test_inne_formaty_odrzucone(self, nazwa):
        with pytest.raises(HTTPException) as e:
            asyncio.run(wczytaj_ikone(plik(nazwa, png(128, 128))))
        assert "PNG" in e.value.detail

    def test_pusty_plik(self):
        with pytest.raises(HTTPException):
            asyncio.run(wczytaj_ikone(plik("logo.png", b"")))

    def test_za_duzy_plik(self):
        with pytest.raises(HTTPException) as e:
            asyncio.run(wczytaj_ikone(plik("logo.png", png(128, 128) + b"\x00" * (600 * 1024))))
        assert "kB" in e.value.detail

    def test_plik_udajacy_png(self):
        with pytest.raises(HTTPException) as e:
            asyncio.run(wczytaj_ikone(plik("logo.png", b"PK\x03\x04 to jest zip")))
        assert "prawidłowy plik PNG" in e.value.detail


class TestKolor:
    @pytest.mark.parametrize("wejscie,wynik", [
        ("#1fc8ba", "#1fc8ba"),
        ("#FFF", "#fff"),
        ("  #A1B2C3  ", "#a1b2c3"),
    ])
    def test_poprawne(self, wejscie, wynik):
        assert sprawdz_kolor(wejscie) == wynik

    @pytest.mark.parametrize("zly", ["czerwony", "rgb(1,2,3)", "#12", "#12345", "", "1fc8ba"])
    def test_niepoprawne(self, zly):
        with pytest.raises(HTTPException):
            sprawdz_kolor(zly)
