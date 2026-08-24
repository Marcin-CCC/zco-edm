"""Makiety ekranów jako PNG — do wstawienia w wersji PowerPointowej.

W HTML makiety są rysowane stylami (ostre w każdej skali). PowerPoint nie zrozumie
tych stylów, a przerysowywanie ich kształtami byłoby pracą bez wartości, więc do PPTX
wstawiamy je jako obrazy renderowane z tego samego źródła — wygląd zostaje ten sam.

    python makiety_png.py
"""
import os
import subprocess
import tempfile
import time

from generuj import KATALOG, STYL, makieta_czat, makieta_pliki

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SZEROKOSC = 560          # szerokość makiety w pikselach (2× dla ostrości = 1120)


def zrzut(nazwa, html_makiety):
    strona = (f"<!doctype html><meta charset='utf-8'><style>{STYL}"
              f"body{{background:#fff;padding:0;margin:0;}}"
              f".ramka{{width:{SZEROKOSC}px;padding:8px;}}</style>"
              f"<div class='ramka'>{html_makiety}</div>")
    html_path = os.path.join(tempfile.mkdtemp(), f"{nazwa}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(strona)
    cel = os.path.join(KATALOG, f"{nazwa}.png")
    if os.path.exists(cel):
        os.remove(cel)
    profil = tempfile.mkdtemp(prefix="makieta_")
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={profil}",
         f"--window-size={SZEROKOSC + 16},480", "--hide-scrollbars",
         "--force-device-scale-factor=2", "--virtual-time-budget=5000",
         f"--screenshot={cel}", f"file:///{html_path.replace(os.sep, '/')}"],
        capture_output=True, timeout=180)
    for _ in range(60):
        if os.path.exists(cel) and os.path.getsize(cel) > 0:
            r = os.path.getsize(cel)
            time.sleep(0.4)
            if os.path.getsize(cel) == r:
                break
        time.sleep(0.4)
    przytnij_biel(cel)
    return cel


def przytnij_biel(sciezka, margines=6):
    """Zrzut ma stałą wysokość okna, więc pod makietą zostaje biel — obcinamy ją,
    żeby w PowerPoincie obraz nie wnosił pustego pasa."""
    from PIL import Image, ImageChops
    img = Image.open(sciezka).convert("RGB")
    tlo = Image.new("RGB", img.size, (255, 255, 255))
    roznica = ImageChops.difference(img, tlo)
    ramka = roznica.getbbox()
    if ramka:
        l, g, p, d = ramka
        img.crop((max(0, l - margines), max(0, g - margines),
                  min(img.width, p + margines), min(img.height, d + margines))).save(sciezka)


def main():
    for nazwa, html in (("makieta-pliki", makieta_pliki()), ("makieta-czat", makieta_czat())):
        cel = zrzut(nazwa, html)
        print(f"  {os.path.basename(cel)}: {os.path.getsize(cel)//1024} KB")


if __name__ == "__main__":
    main()
