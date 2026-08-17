"""Zmniejsza zrzuty ekranu przed wbudowaniem ich w instrukcję.

Zrzuty powstają w gęstości 2× (3200 px szerokości), bo tylko wtedy tekst na nich
jest ostry w druku. Wbudowane w HTML jako data URI dawały jednak plik ważący
kilkanaście megabajtów, a instrukcja otwiera się w aplikacji w ramce — czekanie
kilku sekund na obrazki jest tam odczuwalne.

Dwa kroki, oba bezpieczne dla czytelności:
  * zmniejszenie do 2000 px szerokości — nadal około 170 dpi na szerokość kolumny
    w druku, czyli więcej, niż potrzebuje tekst zrzutu,
  * paleta 256 kolorów — zrzut interfejsu to płaskie plamy barwne i kilka
    gradientów; z ditheringiem różnicy nie widać, a plik chudnie kilkukrotnie.

Uruchomienie:
    python optymalizuj_zrzuty.py [katalog]     # domyślnie zrzuty/
"""
import os
import sys

from PIL import Image

MAKS_SZEROKOSC = 2000
KATALOG = os.path.dirname(os.path.abspath(__file__))


def optymalizuj(sciezka: str) -> tuple[int, int]:
    przed = os.path.getsize(sciezka)
    obraz = Image.open(sciezka).convert("RGB")

    if obraz.width > MAKS_SZEROKOSC:
        wysokosc = round(obraz.height * MAKS_SZEROKOSC / obraz.width)
        obraz = obraz.resize((MAKS_SZEROKOSC, wysokosc), Image.LANCZOS)

    # Dithering ratuje gradienty (tło logowania, pasek boczny) przed pasmowaniem.
    obraz = obraz.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
    obraz.save(sciezka, optimize=True)
    return przed, os.path.getsize(sciezka)


def main():
    korzen = sys.argv[1] if len(sys.argv) > 1 else os.path.join(KATALOG, "zrzuty")
    razem_przed = razem_po = 0
    ile = 0
    for katalog, _, pliki in os.walk(korzen):
        for nazwa in sorted(pliki):
            if not nazwa.lower().endswith(".png"):
                continue
            przed, po = optymalizuj(os.path.join(katalog, nazwa))
            razem_przed += przed
            razem_po += po
            ile += 1
    if ile:
        print(f"{ile} zrzutów: {razem_przed // 1024} KB -> {razem_po // 1024} KB "
              f"({100 - razem_po * 100 // razem_przed}% mniej)")


if __name__ == "__main__":
    main()
