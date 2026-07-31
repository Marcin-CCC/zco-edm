"""Schemat środowiska pracy: komputer deweloperski ↔ Spark DGX.

Rysunek powstaje z danych zebranych ze ŚRODOWISKA, nie z pamięci: `docker ps` na obu
maszynach, zmienne środowiskowe kontenerów, pliki compose, definicje obu przepływów
odczytane z API n8n oraz `systemctl` dla runnera CI. Nazwy kolekcji i modeli sprawdzone
wprost w Qdrancie, Ollamie i vLLM.

Wynik: samodzielny HTML (z osadzonym SVG), plik SVG oraz PDF w formacie A3 poziomo.

    python generuj.py
"""
import os
import subprocess
import tempfile
import time

from stale import DATA, WERSJA_APLIKACJI
from uklad import svg

KATALOG = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

STYL = """
* { box-sizing:border-box; margin:0; }
body { font-family:"Segoe UI",Arial,sans-serif; color:#1e293b; background:#eef2f7; padding:24px; }
.plansza { max-width:1700px; margin:0 auto; background:#fff; border-radius:12px; padding:8px;
           box-shadow:0 8px 30px rgba(29,42,77,.10); }
svg { width:100%; height:auto; display:block; }
.opis { max-width:1700px; margin:22px auto 0; background:#fff; border-radius:12px;
        padding:24px 28px; box-shadow:0 8px 30px rgba(29,42,77,.10); font-size:14px; line-height:1.6; }
.opis h2 { font-size:18px; margin:0 0 10px; color:#1d2a4d; }
.opis h3 { font-size:14.5px; margin:18px 0 6px; color:#1d2a4d; }
.opis ul { margin:0 0 8px; padding-left:20px; }
.opis li { margin-bottom:6px; }
.opis code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:12.5px; }
@page { size:A3 landscape; margin:8mm; }
@media print {
  body { background:#fff; padding:0; }
  .plansza, .opis { box-shadow:none; }
  .opis { break-before:page; }
}
"""

OPIS = f"""
<h2>Jak to czytać</h2>
<p>Rysunek pokazuje DWA tryby pracy tej samej aplikacji. <b>Tryb deweloperski</b>: kod działa
w kontenerach na komputerze lokalnym, ale wszystkie dane i modele bierze ze Sparka — dlatego
szare przerywane linie przecinają granicę stref. <b>Tryb wdrożony</b>: identyczny kod działa
w kontenerach na Sparku i nie sięga poza tę maszynę.</p>

<h3>Co z tego wynika w praktyce</h3>
<ul>
<li><b>Jedna baza danych i jedna baza wektorowa dla obu trybów.</b> Praca deweloperska widzi te same
konta, pliki i rozmowy co wersja demonstracyjna — zmiana danych lokalnie jest zmianą u klienta.
To najważniejsze ograniczenie tego układu.</li>
<li><b>n8n zawsze stoi na Sparku.</b> Lokalny n8n na porcie 5678 należy do innego projektu i nie
uczestniczy w tym przepływie.</li>
<li><b>Odesłania z n8n trafiają pod inny adres w każdym trybie</b> (<code>BACKEND_CALLBACK_URL</code>):
deweloperski <code>192.168.1.17:8001</code>, wdrożony <code>192.168.1.34:8083</code>. To jedyne miejsce,
w którym n8n musi wiedzieć, który backend go zawołał.</li>
<li><b>Pliki wgrane lokalnie są kopiowane na Sparka przez SSH</b>, bo n8n czyta je z wolumenu
<code>/data/shared_docs</code>. Bez tego kroku parsowanie w trybie deweloperskim nie ma czego czytać.</li>
<li><b>Całe wdrożenie dzieje się na Sparku.</b> Runner GitHub Actions działa tam jako usługa systemd:
buduje obrazy natywnie pod ARM64, wypycha do ghcr.io i podnosi kontenery.</li>
</ul>

<h3>Dwa przepływy przez n8n</h3>
<ul>
<li><b>Parsowanie dokumentu</b> — backend wysyła webhook po wgraniu pliku. n8n rozdziela pracę według
formatu: PDF przez rasteryzator i model widzenia, DOCX i ODT przez Docling (ODT najpierw zamieniany
na DOCX), XLSX przez excel-parser. Fragmenty trafiają do Qdranta, a status wraca do backendu.</li>
<li><b>Pytanie w czacie</b> — backend woła webhook strumieniowy. n8n pobiera 15 fragmentów z Qdranta
(z filtrem uprawnień przygotowanym przez backend), odrzuca te poniżej progu trafności 0,50, buduje
kontekst z etykietami źródeł, pyta model i odsyła listę użytych dokumentów do backendu.</li>
</ul>

<h3>Czego na rysunku nie ma</h3>
<p>Pominąłem kontenery innych projektów działających na obu maszynach (iwound-lab, appsmith, comfyui,
open-webui, lokalny n8n) — nie należą do tego środowiska i tylko zaciemniałyby obraz. Pominąłem też
sekrety: nagłówek uwierzytelniający webhooki i hasła baz są w plikach konfiguracyjnych, nie na schemacie.</p>

<h3>Skąd wzięte dane</h3>
<p><code>docker ps</code> na obu maszynach, zmienne środowiskowe kontenerów, <code>docker-compose*.yaml</code>,
<code>backend/.env.dev</code>, definicje obu przepływów odczytane z API n8n oraz <code>systemctl</code>
dla runnera. Stan na {DATA}, aplikacja {WERSJA_APLIKACJI}.</p>
"""


def do_pdf(html_path, pdf_path, limit_sekund=240):
    """Wydruk przez Edge headless (ta sama pułapka co w innych generatorach: proces
    kończy się, zanim dopisze plik — czekamy, aż PDF przestanie rosnąć)."""
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    profil = tempfile.mkdtemp(prefix="arch_pdf_")
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={profil}",
         "--print-to-pdf-no-header", f"--print-to-pdf={pdf_path}",
         "--virtual-time-budget=15000", f"file:///{html_path.replace(os.sep, '/')}"],
        capture_output=True, timeout=limit_sekund)
    poprzedni, stabilne = -1, 0
    for _ in range(limit_sekund * 2):
        if os.path.exists(pdf_path):
            rozmiar = os.path.getsize(pdf_path)
            stabilne = stabilne + 1 if rozmiar == poprzedni and rozmiar > 0 else 0
            poprzedni = rozmiar
            if stabilne >= 3:
                return True
        time.sleep(0.5)
    return os.path.exists(pdf_path)


def main():
    rysunek = svg()
    html = (f"<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
            f"<title>ZCO DM — schemat środowiska</title><style>{STYL}</style></head><body>"
            f"<div class='plansza'>{rysunek}</div>"
            f"<div class='opis'>{OPIS}</div></body></html>")
    html_path = os.path.join(KATALOG, "ZCO-DM-srodowisko.html")
    svg_path = os.path.join(KATALOG, "ZCO-DM-srodowisko.svg")
    pdf_path = os.path.join(KATALOG, "ZCO-DM-srodowisko.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(rysunek)
    ok = do_pdf(html_path, pdf_path)
    print(f"ZCO-DM-srodowisko: {os.path.getsize(html_path)//1024} KB HTML, "
          f"{os.path.getsize(svg_path)//1024} KB SVG, "
          f"{(os.path.getsize(pdf_path)//1024) if ok else 0} KB PDF")


if __name__ == "__main__":
    main()
