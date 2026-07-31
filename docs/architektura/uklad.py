"""Rysunek schematu — sama warstwa graficzna (SVG).

Trasowanie: między strefami biegnie pionowy korytarz (x ≈ 500–536), nad strefami
poziomy (y ≈ 218), a wewnątrz Sparka dwie poziome szyny (y = 558 i y = 716), z których
schodzą krótkie piony do kafelków. Dzięki temu żadna linia nie przecina kafelka ani
cudzej etykiety.
"""
from stale import (DATA, GRANAT, LINIA, NIEBIESKI, POMARANCZ, SZARY, SZEROKOSC, TLO_KARTY,
                   TURKUS, WERSJA_APLIKACJI, WYSOKOSC, lamana, ramka, strefa, strzalka)


def svg():
    e = []
    for kolor in (GRANAT, TURKUS, NIEBIESKI, POMARANCZ, SZARY):
        e.append(f'<marker id="grot-{kolor.lstrip("#")}" viewBox="0 0 10 10" refX="9" refY="5" '
                 f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                 f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{kolor}"/></marker>')
    s = ["<defs>" + "".join(e) + "</defs>"]

    s.append(f'<text x="40" y="46" font-size="27" font-weight="700" fill="{GRANAT}">'
             f'ZCO Document Management — środowisko pracy i wdrożenia</text>')
    s.append(f'<text x="40" y="72" font-size="14" fill="{SZARY}">'
             f'Stan na {DATA} · aplikacja {WERSJA_APLIKACJI} · adresy i porty odczytane z działających '
             f'kontenerów, plików compose i definicji przepływów w n8n</text>')

    # ------------------------------------------------------------ CI/CD (góra)
    s.append(strefa(40, 96, 1600, 100,
                    "GitHub · CI/CD — wypchnięcie na master buduje obrazy i podnosi kontenery na Sparku",
                    "", NIEBIESKI))
    s.append(ramka(70, 138, 236, 52, "Repozytorium", "github.com/Marcin-CCC/zco-edm", NIEBIESKI))
    s.append(ramka(346, 138, 236, 52, "GitHub Actions", "job „build” · ubuntu-latest", NIEBIESKI))
    s.append(ramka(622, 138, 268, 52, "ghcr.io", "backend:latest · frontend:latest", NIEBIESKI))
    s.append(ramka(930, 138, 300, 52, "Runner self-hosted na Sparku",
                   "usługa systemd: spark-zco-edm", NIEBIESKI))
    s.append(ramka(1270, 138, 340, 52, "docker compose --profile spark",
                   "up -d backend frontend → nowe kontenery", NIEBIESKI))
    for x1, x2 in ((306, 342), (582, 618), (890, 926), (1230, 1266)):
        s.append(strzalka(x1, 164, x2, 164, "", NIEBIESKI))

    # ------------------------------------------------------------ strefy
    s.append(strefa(40, 250, 470, 700, "Komputer lokalny (Windows)",
                    "192.168.1.17 · Docker Desktop · praca deweloperska", GRANAT))
    s.append(strefa(560, 250, 1080, 810, "Spark DGX (Ubuntu)",
                    "192.168.1.34 · 128 GB pamięci zunifikowanej · usługi AI, dane, wdrożenie",
                    TURKUS))

    # ------------------------------------------------------------ komputer lokalny
    s.append(ramka(70, 318, 410, 66, "Przeglądarka dewelopera",
                   "localhost:3002 — interfejs | localhost:8001/docs — API", tlo=TLO_KARTY))
    s.append(ramka(70, 420, 410, 78, "frontend (kontener)",
                   "zco-edm-final-frontend-1 · Next.js | 3002 → 3000 | proxy /api → backend:8001",
                   tlo=TLO_KARTY))
    s.append(ramka(70, 536, 410, 96, "backend (kontener)",
                   "zco-edm-final-backend-1 · FastAPI | 8001 → 8000 | kod montowany z dysku "
                   "(backend/app) | konfiguracja: backend/.env.dev", tlo=TLO_KARTY))
    s.append(ramka(70, 670, 410, 66, "Narzędzia dokumentacji",
                   "Edge headless: zrzuty ekranu i PDF | docs/instrukcje, docs/prezentacja",
                   kolor=SZARY, tlo=TLO_KARTY))
    s.append(ramka(70, 774, 410, 66, "Git + Claude Code",
                   "kod, testy, pomiary | wypchnięcie na master = wdrożenie",
                   kolor=SZARY, tlo=TLO_KARTY))
    s.append(strzalka(275, 384, 275, 416, "", GRANAT))
    s.append(strzalka(275, 498, 275, 532, "HTTP", GRANAT))
    s.append(lamana([(275, 246), (275, 200)], "", NIEBIESKI, True))
    s.append(f'<text x="285" y="228" font-size="11.5" fill="{NIEBIESKI}">git push na master</text>')

    # ------------------------------------------------------------ Spark: aplikacja
    s.append(ramka(590, 318, 300, 78, "edm-frontend",
                   "obraz z ghcr | 3000 → 3000 | wersja dla klienta", tlo=TLO_KARTY))
    s.append(ramka(920, 318, 300, 78, "edm-backend",
                   "obraz z ghcr | 8083 → 8000 | ten sam kod co lokalnie", tlo=TLO_KARTY))
    s.append(ramka(1250, 318, 360, 78, "edm-zco-postgres",
                   "PostgreSQL 15 | 5433 → 5432 | konta, pliki, rozmowy",
                   kolor=TURKUS, tlo=TLO_KARTY))
    s.append(strzalka(890, 357, 916, 357, "", GRANAT))
    s.append(strzalka(1220, 357, 1246, 357, "SQL", TURKUS))

    # ------------------------------------------------------------ Spark: n8n i pliki
    s.append(ramka(920, 442, 380, 96, "n8n_spark",
                   "5678 · tunel: n8n-spark.polmedi.com | parsowanie dokumentu (47 węzłów) | "
                   "czat z bazy wiedzy (webhook strumieniowy)", kolor=POMARANCZ, tlo="#fff7ed"))
    s.append(ramka(1340, 442, 270, 96, "Wolumen dokumentów",
                   "zco-edm-app_shared_docs | /data/shared_docs | oryginały wgranych plików",
                   kolor=TURKUS, tlo=TLO_KARTY))
    s.append(strzalka(1070, 396, 1070, 438, "webhook + nagłówek sekretu", POMARANCZ))
    s.append(strzalka(1304, 490, 1336, 490, "", TURKUS))
    s.append(f'<text x="1226" y="524" font-size="11.5" fill="{TURKUS}">odczyt pliku</text>')
    s.append(lamana([(916, 466), (876, 466), (876, 357), (886, 357)], "", POMARANCZ, True))
    s.append(f'<text x="640" y="430" font-size="11.5" fill="{POMARANCZ}">'
             f'odesłanie: status pliku i lista źródeł odpowiedzi</text>')

    # ------------------------------------------------------------ Spark: parsowanie
    s.append(f'<text x="590" y="582" font-size="14" font-weight="700" fill="{GRANAT}">'
             f'Usługi przetwarzania dokumentów</text>')
    s.append(ramka(590, 596, 320, 84, "edm-docling-spark",
                   "8085 → 5001 | /v1/convert/file | tekst i tabele", tlo=TLO_KARTY))
    s.append(ramka(940, 596, 320, 84, "zco-document-rasterizer",
                   "8084 | /rasterize (PDF → obrazy) | /convert-to-docx (ODT → DOCX)",
                   tlo=TLO_KARTY))
    s.append(ramka(1290, 596, 320, 84, "excel-parser",
                   "8086 | /process-excel | arkusze XLSX", tlo=TLO_KARTY))

    # ------------------------------------------------------------ Spark: modele i wektory
    s.append(f'<text x="590" y="742" font-size="14" font-weight="700" fill="{GRANAT}">'
             f'Modele i baza wektorowa</text>')
    s.append(ramka(590, 756, 320, 96, "qwen3vl-vllm",
                   "8002 | Qwen/Qwen3-VL-30B-A3B-Instruct | odpowiedzi czatu, rozpoznawanie "
                   "dokumentów, streszczenia", kolor=TURKUS, tlo=TLO_KARTY))
    s.append(ramka(940, 756, 320, 96, "ollama",
                   "11434 | bge-m3:latest | zamiana tekstu na wektory: fragmenty, pytania, "
                   "streszczenia", kolor=TURKUS, tlo=TLO_KARTY))
    s.append(ramka(1290, 756, 320, 96, "qdrant",
                   "6333 | chi_camp_2026 — fragmenty | chi_camp_2026_streszczenia — opisy",
                   kolor=TURKUS, tlo=TLO_KARTY))

    # szyna 1: n8n → usługi parsowania
    s.append(f'<path d="M 1110 538 L 1110 558 M 750 558 L 1450 558" stroke="{POMARANCZ}" '
             f'stroke-width="1.8" fill="none"/>')
    for x in (750, 1100, 1450):
        s.append(strzalka(x, 558, x, 592, "", POMARANCZ))
    s.append(f'<text x="590" y="552" font-size="11.5" fill="{POMARANCZ}">'
             f'n8n woła usługi parsowania (HTTP)</text>')

    # szyna 2: n8n → modele i wektory (pion w wolnym korytarzu między kafelkami)
    s.append(f'<path d="M 1275 558 L 1275 716 M 750 716 L 1450 716" stroke="{POMARANCZ}" '
             f'stroke-width="1.8" fill="none"/>')
    for x in (750, 1100, 1450):
        s.append(strzalka(x, 716, x, 752, "", POMARANCZ))
    s.append(f'<text x="590" y="710" font-size="11.5" fill="{POMARANCZ}">'
             f'wektoryzacja pytań i fragmentów, zapis do bazy wektorowej</text>')

    # backend na Sparku → modele wprost (prawą krawędzią, bez przecięć)
    s.append(lamana([(1160, 396), (1160, 416), (1628, 416), (1628, 900), (1450, 900), (1450, 856)],
                    "", GRANAT, True))
    s.append(f'<text x="1058" y="916" font-size="11.5" fill="{GRANAT}">'
             f'backend wprost do modeli i wektorów (streszczenia, rozpoznawanie, wyszukiwanie)</text>')

    # ------------------------------------------------------------ połączenia deweloperskie
    s.append(lamana([(480, 560), (536, 560), (536, 218), (1430, 218), (1430, 314)], "", SZARY, True))
    s.append(f'<text x="860" y="212" font-size="11.5" fill="{SZARY}">'
             f'tryb deweloperski: ta sama baza danych (5433)</text>')
    s.append(lamana([(480, 580), (524, 580), (524, 466), (912, 466)], "", SZARY, True))
    s.append(f'<text x="600" y="484" font-size="11.5" fill="{SZARY}">'
             f'webhook parsowania (tryb deweloperski)</text>')
    s.append(f'<text x="546" y="700" font-size="12" font-weight="600" fill="{SZARY}" '
             f'transform="rotate(-90 546 700)" text-anchor="middle">'
             f'korytarz trybu deweloperskiego</text>')
    s.append(lamana([(480, 620), (500, 620), (500, 936), (1625, 936), (1625, 490), (1614, 490)],
                    "", SZARY, True))
    s.append(f'<text x="620" y="930" font-size="11.5" fill="{SZARY}">'
             f'kopiowanie wgranych plików przez SSH do /data/shared_docs</text>')

    # ------------------------------------------------------------ użytkownik końcowy
    s.append(ramka(620, 950, 420, 70, "Przeglądarka użytkownika (sieć szpitala)",
                   "192.168.1.34:3000 — aplikacja | ruch nie opuszcza sieci lokalnej", tlo="#eff6ff"))
    s.append(f'<path d="M 616 985 L 575 985 L 575 400" stroke="{GRANAT}" stroke-width="1.8" '
             f'fill="none" marker-end="url(#grot-{GRANAT.lstrip("#")})"/>')
    s.append(f'<text x="571" y="700" font-size="11.5" fill="{GRANAT}" '
             f'transform="rotate(-90 571 700)" text-anchor="middle">HTTP</text>')

    # ------------------------------------------------------------ legenda
    s.append(ramka(40, 1090, 1600, 76, "Legenda", "", kolor=LINIA))
    legenda = [
        (GRANAT, False, "wywołania aplikacji (HTTP, SQL)"),
        (POMARANCZ, False, "przepływy w n8n: parsowanie i czat"),
        (SZARY, True, "połączenia zestawiane tylko w trybie deweloperskim"),
        (NIEBIESKI, False, "budowanie i wdrożenie (CI/CD)"),
    ]
    for i, (kolor, przerywana, opis) in enumerate(legenda):
        gx, gy = 66 + (i % 2) * 800, 1128 + (i // 2) * 24
        kreska = ' stroke-dasharray="6 4"' if przerywana else ""
        s.append(f'<path d="M {gx} {gy} L {gx + 30} {gy}" stroke="{kolor}" stroke-width="2"{kreska}/>')
        s.append(f'<text x="{gx + 40}" y="{gy + 4}" font-size="12.5" fill="{SZARY}">{opis}</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SZEROKOSC} {WYSOKOSC}" '
            f'width="{SZEROKOSC}" height="{WYSOKOSC}" font-family="Segoe UI, Arial, sans-serif">'
            f'<rect width="{SZEROKOSC}" height="{WYSOKOSC}" fill="#ffffff"/>' + "".join(s) + "</svg>")
