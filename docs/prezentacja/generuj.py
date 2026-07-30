"""Generator prezentacji sprzedażowej ZCO Document Management (HTML + PDF).

Slajd ma stały rozmiar 1280×720 px (16:9). Na ekranie skalujemy go do okna
(przelicznik liczy JS), w druku strona ma dokładnie 338,667×190,5 mm — czyli te
same 1280×720 px przy 96 dpi — więc jeden slajd to jedna strona PDF bez marginesu.

Kolory marki i ich rola (sprawdzone walidatorem palet, tryb jasny):
  #1d2a4d  granat — tło paneli i kolor pisma, NIE służy jako kolor znaczników,
  #1fc8ba  turkus marki — wyłącznie na granatowym tle (kontrast 6,73:1);
           na białym miałby 2,04:1, czyli poniżej progu 3:1 dla elementów graficznych,
  #0f9b8e  turkus przyciemniony — znaczniki na białym (kontrast 3,4:1, ten sam odcień),
  #2563eb  niebieski aplikacji — druga seria; para #0f9b8e/#2563eb przechodzi komplet
           testów (rozróżnialność przy zaburzeniach widzenia barw ΔE 21,3).
Każdy znacznik ma podpis wprost przy sobie, więc kolor nigdy nie niesie znaczenia sam.

Uruchomienie:
    python generuj.py
"""
import base64
import os
import subprocess
import tempfile
import time

KATALOG = os.path.dirname(os.path.abspath(__file__))
ZRZUTY = os.path.join(os.path.dirname(KATALOG), "instrukcje", "zrzuty")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

WERSJA = "1.0.2"
DATA = "30 lipca 2026"

GRANAT = "#1d2a4d"
TURKUS = "#1fc8ba"
TURKUS_CIEMNY = "#0f9b8e"
NIEBIESKI = "#2563eb"


def obraz(plik):
    sciezka = os.path.join(ZRZUTY, plik)
    if not os.path.exists(sciezka):
        print(f"  UWAGA: brak zrzutu {plik}")
        return None
    with open(sciezka, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def punkty(*tresc):
    return "<ul class='punkty'>" + "".join(f"<li>{t}</li>" for t in tresc) + "</ul>"


# ---------------------------------------------------------------- infografiki

def graf_bezpieczenstwo():
    """Gdzie fizycznie dzieje się przetwarzanie — wszystko w jednym budynku."""
    return f"""
<div class="graf-bezp">
  <div class="budynek">
    <div class="budynek-etykieta">Szpital · Wasza serwerownia</div>
    <div class="kafle">
      <div class="kafel"><span class="ikona">🖥️</span><b>Aplikacja</b><span>przeglądarka pracownika</span></div>
      <div class="kafel"><span class="ikona">🧠</span><b>Model językowy</b><span>działa na Waszym urządzeniu</span></div>
      <div class="kafel"><span class="ikona">🗄️</span><b>Dokumenty i indeks</b><span>dysk w serwerowni</span></div>
    </div>
  </div>
  <div class="mur">
    <div class="mur-linia"></div>
    <div class="mur-podpis">brak połączenia<br>z usługami zewnętrznymi</div>
  </div>
  <div class="chmura">
    <div class="chmura-ikona">☁️</div>
    <b>Internet</b>
    <span>nie wychodzi tu żaden dokument,<br>fragment ani pytanie</span>
  </div>
</div>"""


def graf_sciezka():
    """Cztery kroki od pytania do sprawdzalnej odpowiedzi."""
    kroki = [
        ("1", "Pytanie", "zwykłym językiem, np. „jak rozliczyć delegację?”"),
        ("2", "Wyszukanie", "system znajduje fragmenty w Waszych plikach"),
        ("3", "Odpowiedź", "zbudowana wyłącznie z tych fragmentów"),
        ("4", "Dowód", "numer przy zdaniu prowadzi do dokumentu i strony"),
    ]
    kafle = "".join(
        f"<div class='krok'><div class='krok-numer'>{n}</div>"
        f"<b>{t}</b><span>{o}</span></div>"
        + ("<div class='strzalka'>→</div>" if n != "4" else "")
        for n, t, o in kroki
    )
    return f"<div class='graf-sciezka'>{kafle}</div>"


def graf_liczby():
    """Kafelki z liczbami + porównanie dwóch czasów (znaczniki z podpisami wprost)."""
    kafelki = [
        ("128 GB", "pamięci dla modelu", "jedno urządzenie obsługuje cały szpital"),
        ("4 TB", "na dokumenty", "setki tysięcy plików biurowych"),
        ("~1 s", "do pierwszego słowa odpowiedzi", "cała odpowiedź gotowa w ok. 15 s"),
    ]
    kafle = "".join(
        f"<div class='liczba'><div class='liczba-duza'>{d}</div>"
        f"<div class='liczba-opis'>{o}</div><div class='liczba-nota'>{n}</div></div>"
        for d, o, n in kafelki
    )
    # Dwa słupki: proporcja długości = proporcja czasów (15 s i 60 s), podpisy przy słupkach
    return f"""
<div class='graf-liczby'>{kafle}</div>
<div class='slupki'>
  <div class='slupki-tytul'>Ile to trwa w praktyce</div>
  <div class='slupek-wiersz'>
    <span class='slupek-nazwa'>Czas do rozpoczęcia odpowiedzi</span>
    <span class='slupek-tor'><span class='slupek' style='width:1.67%;background:{TURKUS_CIEMNY}'></span></span>
    <span class='slupek-wartosc'>ok. 1 s</span>
  </div>
  <div class='slupek-wiersz'>
    <span class='slupek-nazwa'>Czas utworzenia całej odpowiedzi</span>
    <span class='slupek-tor'><span class='slupek' style='width:25%;background:{TURKUS_CIEMNY}'></span></span>
    <span class='slupek-wartosc'>ok. 15 s</span>
  </div>
  <div class='slupek-wiersz'>
    <span class='slupek-nazwa'>Przygotowanie dokumentu</span>
    <span class='slupek-tor'><span class='slupek' style='width:100%;background:{NIEBIESKI}'></span></span>
    <span class='slupek-wartosc'>średnio ok. 60 s</span>
  </div>
  <div class='slupki-nota'>Długość słupka odpowiada czasowi. Pomiary z działającego wdrożenia
    demonstracyjnego (157 dokumentów); przygotowanie dokumentu odbywa się raz, w tle, przy wgraniu pliku.</div>
</div>"""


def graf_harmonogram():
    etapy = [
        ("Tydzień 1", "Instalacja i uruchomienie", "urządzenie w serwerowni, konta, uprawnienia"),
        ("Tydzień 2", "Wasze dokumenty i wzorce", "wgrywamy pierwszą partię, układamy schematy pism"),
        ("Tydzień 3", "Szkolenia i start", "20 min dla użytkownika, 2 h dla administratora"),
    ]
    return "<div class='harmonogram'>" + "".join(
        f"<div class='etap'><div class='etap-kropka'></div>"
        f"<div class='etap-tydzien'>{t}</div><b>{n}</b><span>{o}</span></div>"
        for t, n, o in etapy
    ) + "</div>"


def graf_zastosowania():
    dzialy = [
        ("Kadry", "regulaminy, wnioski, PPK, ZFŚS"),
        ("Jakość i akredytacja", "procedury, instrukcje, wersje obowiązujące"),
        ("Personel medyczny", "procedury kliniczne i pielęgniarskie"),
        ("Administracja", "umowy, zarządzenia, przetargi"),
        ("BHP · RODO · IT", "polityki i instrukcje wewnętrzne"),
        ("Poza szpitalem", "uczelnie, urzędy, kancelarie, produkcja"),
    ]
    return "<div class='siatka-dzialow'>" + "".join(
        f"<div class='dzial'><b>{n}</b><span>{o}</span></div>" for n, o in dzialy
    ) + "</div>"


def graf_cennik():
    return f"""
<table class='cennik'>
  <tr><th>Pozycja</th><th class='kwota'>Netto</th></tr>
  <tr><td>Sprzęt: NVIDIA DGX Spark — 128 GB pamięci, 4 TB SSD</td><td class='kwota'>20 000 zł</td></tr>
  <tr><td>Dostawa i wdrożenie oprogramowania</td><td class='kwota'>25 000 zł</td></tr>
  <tr><td>Wsparcie i rozwój</td><td class='kwota'>1 000 zł / mies.</td></tr>
  <tr class='suma'><td>Rok pierwszy łącznie</td><td class='kwota'>57 000 zł</td></tr>
</table>
<div class='cennik-nota'>
  <div><b>Bez opłat za użytkownika</b> i bez opłat za liczbę dokumentów.</div>
  <div><b>Sprzęt zostaje Wasz</b> — nie płacicie abonamentu za dostęp do własnych danych.</div>
  <div>Trzy lata użytkowania: <b>81 000 zł netto</b>.</div>
</div>"""


# ---------------------------------------------------------------- slajdy

SLAJDY = [
    {
        "typ": "okladka",
        "tytul": "ZCO Document Management",
        "podtytul": "Pytasz jak człowieka. Odpowiada z Waszych dokumentów.<br>Nic nie wychodzi poza szpital.",
        "notatka": "Trzy rzeczy do zapamiętania: odpowiedzi wskazują dokument źródłowy, "
                   "dane nie opuszczają budynku, obsługa to wpisanie pytania.",
    },
    {
        "tytul": "Problem, który znają wszyscy",
        "puenta": "Wiedza jest w dokumentach. Problemem jest droga do niej.",
        "tresc": punkty(
            "Dokument jest — tylko nie wiadomo, w którym folderze i <b>która wersja obowiązuje</b>",
            "Nowy pracownik pyta koleżankę zamiast szukać w regulaminie",
            "Ta sama odpowiedź udzielana dziesiątki razy przez kadry i dział jakości",
            "Przy akredytacji i kontroli liczy się <b>czas dotarcia do właściwego zapisu</b>",
            "Chmura odpada: dokumenty wewnętrzne nie mogą trafiać do zewnętrznego dostawcy",
        ),
        "notatka": "To nie brak dokumentów, tylko czas dostępu i pewność wersji. Każde „gdzie to jest?” "
                   "kosztuje dwie osoby — pytającego i tę, która odpowiada.",
    },
    {
        "tytul": "Co dostajecie",
        "puenta": "Trzy drogi do dokumentu — pracownik wybiera tę, która jest mu bliższa.",
        "tresc": punkty(
            "<b>Repozytorium</b> — foldery, uprawnienia, statusy przetwarzania",
            "<b>Baza wiedzy</b> — pytanie zwykłym językiem, odpowiedź z odnośnikami do stron",
            "<b>Wyszukiwarka po polach</b> — „zarządzenia z 2024”, „procedury zatwierdzone przez…”",
            "<b>Automatyczne rozpoznawanie</b> — rodzaj pisma, numer, data, osoba zatwierdzająca",
            "Instrukcja obsługi wbudowana w aplikację",
        ),
        "obraz": "a02-pliki.png",
        "notatka": "Trzy drogi do dokumentu: przeglądanie, pytanie o treść, wyszukiwanie po opisie. "
                   "Pracownik wybiera bliższą sobie.",
    },
    {
        "tytul": "Bezpieczeństwo i prywatność",
        "puenta": "Żaden dokument, fragment ani pytanie nie opuszcza Waszej sieci.",
        "tresc": graf_bezpieczenstwo() + punkty(
            "Dostęp do folderów nadawany rolom — użytkownik widzi tylko swoje, także w czacie",
            "Historia pytań prywatna; administrator widzi statystyki, nie cudze rozmowy",
            "Automatyczne wylogowanie po bezczynności, zmiana hasła za potwierdzeniem",
        ),
        "notatka": "Tu jest różnica wobec chmury: pytanie o dokument kadrowy nie wychodzi z organizacji. "
                   "Przez sieć idzie tylko ruch przeglądarka–serwer.",
    },
    {
        "tytul": "Skąd pewność, że odpowiedź jest prawdziwa",
        "puenta": "Nie trzeba wierzyć systemowi — każde zdanie sprawdzicie w źródle.",
        "tresc": graf_sciezka() + punkty(
            "Odpowiedź powstaje <b>wyłącznie</b> z fragmentów Waszych plików",
            "Brak dopasowania = jasny komunikat zamiast wymyślonej treści",
            "Widać też, ile dokumentów sprawdzono i z których nie skorzystano",
        ),
        "notatka": "Jak cytowanie w publikacji — każde twierdzenie sprawdzalne w dwie sekundy. "
                   "Warunek konieczny przy procedurach medycznych.",
    },
    {
        "tytul": "Pojemność i szybkość",
        "puenta": "Baza rośnie, czas odpowiedzi stoi w miejscu.",
        "tresc": graf_liczby(),
        "notatka": "Liczby z działającego wdrożenia, nie z folderu producenta. Pojemność ogranicza dysk, "
                   "nie wydajność. Urządzenie wielkości książki, pobór prądu jak stacja robocza.",
    },
    {
        "tytul": "Łatwość obsługi",
        "puenta": "Kto umie korzystać z wyszukiwarki internetowej, umie korzystać z tego.",
        "tresc": punkty(
            "Przeglądarka — nic do instalowania na komputerach pracowników",
            "Trzy ekrany: <b>Dashboard</b>, <b>Pliki</b>, <b>Baza wiedzy</b>. Administracja tylko dla administratora",
            "Pytanie potoczne działa: „delegacja” znajdzie „podróż służbową”, „L4” — „zwolnienie lekarskie”",
            "Wystarczy sama nazwa dokumentu, żeby dostać jego opis i odnośnik",
            "<b>Szkolenie pracownika: 20 minut.</b> Instrukcja w aplikacji, pod przyciskiem Pomoc",
        ),
        "obraz": "a08-chat.png",
        "notatka": "Sprawdzianem jest osoba, która nie chce uczyć się nowego programu. "
                   "Kto umie korzystać z wyszukiwarki, umie korzystać z tego.",
    },
    {
        "tytul": "Gdzie to pracuje",
        "puenta": "Kolejny dział to wgranie dokumentów, a nie nowe wdrożenie.",
        "tresc": graf_zastosowania() + punkty(
            "Zaczynamy zwykle od kadr — tam pytania powtarzają się najczęściej, efekt widać w pierwszym tygodniu",
            "Rozszerzenie na kolejny dział to wgranie dokumentów i nadanie uprawnień, nie nowe wdrożenie",
        ),
        "notatka": "Ten sam system sprawdzi się wszędzie tam, gdzie jest duży zasób dokumentów wewnętrznych.",
    },
    {
        "tytul": "Nasza rola: wdrożenie i wsparcie",
        "puenta": "Przychodzimy z Waszymi dokumentami już w środku.",
        "tresc": graf_harmonogram() + punkty(
            "<b>Nie zostawiamy pustego systemu</b> — pierwsza partia dokumentów wgrana i sprawdzona przez nas",
            "<b>Wzorce pod Wasze pisma</b> — system sam wyciąga numer, datę i osobę zatwierdzającą",
            "<b>Wsparcie miesięczne</b> — aktualizacje, opieka nad jakością odpowiedzi, nowe rodzaje dokumentów",
            "<b>Kierunek rozwoju</b> (poza obecną wersją): powiązania między dokumentami i wersja obowiązująca, "
            "podgląd PDF na cytowanej stronie, logowanie kontem domenowym, integracja z systemem szpitalnym",
        ),
        "notatka": "Najczęstszy powód, dla którego takie systemy umierają, to pusty start. "
                   "Ostatni punkt to plan — tych elementów nie ma jeszcze w wersji pokazywanej dziś.",
    },
    {
        "tytul": "Warunki i następny krok",
        "tresc": graf_cennik(),
        "puenta": "Następny krok: dwutygodniowe uruchomienie próbne na Waszych dokumentach kadrowych "
                  "— u Was, bez zobowiązania.",
        "notatka": "Nie proszę o decyzję zakupową, tylko o test na własnych dokumentach. "
                   "Jeśli po dwóch tygodniach kadry powiedzą, że to nie pomaga — rozstajemy się bez kosztów.",
    },
]

STYL = f"""
:root {{
  --granat:{GRANAT}; --turkus:{TURKUS}; --turkus-ciemny:{TURKUS_CIEMNY}; --niebieski:{NIEBIESKI};
  --tekst:#1e293b; --szary:#64748b; --linia:#e2e8f0; --tlo:#f8fafc;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:"Segoe UI",Arial,sans-serif; color:var(--tekst); background:#e5e7eb; }}

.slajd {{ width:1280px; height:720px; background:#fff; position:relative; overflow:hidden;
         display:flex; flex-direction:column; padding:56px 64px 48px; }}
.slajd + .slajd {{ margin-top:24px; }}
.slajd h2 {{ font-size:40px; line-height:1.15; color:var(--granat); margin-bottom:8px; }}
.slajd h2::after {{ content:""; display:block; width:64px; height:5px; background:var(--turkus);
                   border-radius:3px; margin-top:14px; }}
.tresc {{ flex:1; display:flex; flex-direction:column; gap:20px; margin-top:26px; min-height:0; }}
.tresc.z-obrazem {{ flex-direction:row; align-items:flex-start; gap:36px; }}
.tresc.z-obrazem .kolumna {{ flex:1 1 52%; min-width:0; }}
.tresc.z-obrazem figure {{ flex:1 1 48%; min-width:0; }}
.tresc.z-obrazem.obraz-maly figure {{ flex:0 0 38%; }}
figure img {{ width:100%; border:1px solid var(--linia); border-radius:8px;
             box-shadow:0 8px 24px rgba(29,42,77,.12); display:block; }}

ul.punkty {{ list-style:none; }}
ul.punkty li {{ position:relative; padding-left:32px; margin-bottom:20px; font-size:23px; line-height:1.45; }}
ul.punkty li::before {{ content:""; position:absolute; left:4px; top:13px; width:11px; height:11px;
                       border-radius:50%; background:var(--turkus-ciemny); }}

/* --- infografika: bezpieczeństwo --- */
.graf-bezp {{ display:flex; align-items:stretch; gap:0; }}
.budynek {{ flex:1; background:var(--granat); border-radius:12px; padding:18px 20px 20px; }}
.budynek-etykieta {{ color:var(--turkus); font-size:15px; font-weight:600; letter-spacing:.06em;
                    text-transform:uppercase; margin-bottom:14px; }}
.kafle {{ display:flex; gap:12px; }}
.kafel {{ flex:1; background:rgba(255,255,255,.08); border-radius:9px; padding:16px 18px; color:#fff; }}
.kafel .ikona {{ font-size:26px; display:block; margin-bottom:6px; }}
.kafel b {{ display:block; font-size:18px; margin-bottom:3px; }}
.kafel span {{ font-size:14px; color:#cbd5e1; line-height:1.35; }}
.mur {{ width:96px; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.mur-linia {{ width:0; height:78px; border-left:4px dashed #cbd5e1; }}
.mur-podpis {{ font-size:12px; color:var(--szary); text-align:center; margin-top:8px; line-height:1.3; }}
.chmura {{ width:250px; border:2px dashed var(--linia); border-radius:12px; padding:14px 16px;
          text-align:center; display:flex; flex-direction:column; justify-content:center; }}
.chmura-ikona {{ font-size:26px; filter:grayscale(1); opacity:.5; }}
.chmura b {{ font-size:16px; color:var(--szary); margin:4px 0 4px; }}
.chmura span {{ font-size:12.5px; color:var(--szary); line-height:1.35; }}

/* --- infografika: ścieżka odpowiedzi --- */
.graf-sciezka {{ display:flex; align-items:stretch; gap:8px; }}
.krok {{ flex:1; background:var(--tlo); border:1px solid var(--linia); border-radius:10px; padding:16px 18px; }}
.krok-numer {{ width:26px; height:26px; border-radius:50%; background:var(--turkus-ciemny); color:#fff;
              font-size:14px; font-weight:700; display:flex; align-items:center; justify-content:center;
              margin-bottom:8px; }}
.krok b {{ display:block; font-size:19px; color:var(--granat); margin-bottom:3px; }}
.krok span {{ font-size:14.5px; color:var(--szary); line-height:1.35; }}
.strzalka {{ align-self:center; color:var(--turkus-ciemny); font-size:22px; }}

/* --- infografika: liczby i czasy --- */
.graf-liczby {{ display:flex; gap:18px; }}
.liczba {{ flex:1; border:1px solid var(--linia); border-radius:12px; padding:26px 24px; background:var(--tlo); }}
.liczba-duza {{ font-size:58px; font-weight:700; color:var(--granat); line-height:1; }}
.liczba-opis {{ font-size:19px; color:var(--tekst); margin-top:6px; }}
.liczba-nota {{ font-size:14px; color:var(--szary); margin-top:6px; line-height:1.35; }}
.slupki {{ border-top:1px solid var(--linia); padding-top:18px; }}
.slupki-tytul {{ font-size:15px; font-weight:600; color:var(--granat); margin-bottom:12px; }}
.slupek-wiersz {{ display:flex; align-items:center; gap:14px; margin-bottom:10px; }}
.slupek-nazwa {{ width:300px; font-size:17px; color:var(--tekst); }}
.slupek-tor {{ flex:0 0 620px; height:20px; }}
.slupek {{ display:block; height:100%; border-radius:4px; }}
.slupek-wartosc {{ font-size:17px; font-weight:600; color:var(--tekst); }}
.slupki-nota {{ font-size:12.5px; color:var(--szary); margin-top:4px; line-height:1.4; }}

/* --- infografika: harmonogram --- */
.harmonogram {{ display:flex; gap:14px; }}
.etap {{ flex:1; border-left:3px solid var(--turkus); padding:4px 16px 8px; position:relative; }}
.etap-kropka {{ position:absolute; left:-9px; top:6px; width:15px; height:15px; border-radius:50%;
               background:var(--turkus-ciemny); border:3px solid #fff; }}
.etap-tydzien {{ font-size:13px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
                color:var(--turkus-ciemny); margin-bottom:4px; }}
.etap b {{ display:block; font-size:21px; color:var(--granat); margin-bottom:4px; }}
.etap span {{ font-size:15.5px; color:var(--szary); line-height:1.4; }}

/* --- infografika: zastosowania --- */
.siatka-dzialow {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.dzial {{ border:1px solid var(--linia); border-radius:10px; padding:18px 20px; background:var(--tlo); }}
.dzial b {{ display:block; font-size:20px; color:var(--granat); margin-bottom:4px; }}
.dzial span {{ font-size:15px; color:var(--szary); line-height:1.35; }}

/* --- cennik --- */
table.cennik {{ width:100%; border-collapse:collapse; font-size:20px; }}
table.cennik th {{ text-align:left; font-size:14px; letter-spacing:.06em; text-transform:uppercase;
                  color:var(--szary); padding:0 0 10px; border-bottom:2px solid var(--linia); }}
table.cennik th.kwota, table.cennik td.kwota {{ text-align:right; white-space:nowrap; }}
table.cennik td {{ padding:14px 0; border-bottom:1px solid var(--linia); }}
table.cennik tr.suma td {{ font-weight:700; color:var(--granat); font-size:23px; border-bottom:none;
                          padding-top:18px; }}
.cennik-nota {{ display:flex; gap:28px; margin-top:20px; }}
.cennik-nota div {{ flex:1; font-size:15px; color:var(--tekst); line-height:1.45;
                   border-left:3px solid var(--turkus); padding-left:12px; }}

.stopka-slajdu {{ margin-top:auto; padding-top:18px; font-size:20px; color:var(--granat); }}
.puenta {{ margin-top:auto; margin-bottom:6px; background:var(--granat); color:#fff; border-radius:10px;
          padding:16px 22px; font-size:22px; font-weight:600; line-height:1.35;
          border-left:6px solid var(--turkus); }}
.stopka-slajdu + .puenta {{ margin-top:16px; }}

/* --- okładka --- */
.slajd.okladka {{ background:var(--granat); color:#fff; justify-content:center; }}
.slajd.okladka .kreska {{ width:88px; height:6px; background:var(--turkus); border-radius:3px; margin-bottom:36px; }}
.slajd.okladka h1 {{ font-size:64px; line-height:1.08; margin-bottom:22px; }}
.slajd.okladka .obietnica {{ font-size:26px; line-height:1.5; color:var(--turkus); max-width:840px; }}
.slajd.okladka .meta {{ position:absolute; left:64px; bottom:48px; font-size:16px; color:#94a3b8; }}
.slajd.okladka .meta b {{ color:#e2e8f0; }}

/* --- numer i stopka slajdu --- */
.numer {{ position:absolute; right:32px; bottom:22px; font-size:13px; color:#94a3b8; }}
.marka {{ position:absolute; left:64px; bottom:22px; font-size:13px; color:#94a3b8; }}

/* --- notatki prelegenta (tylko ekran, przełącznik N) --- */
.notatka {{ display:none; background:#fffbeb; border:1px solid #fde68a; border-radius:8px;
           padding:12px 16px; font-size:15px; color:#78350f; width:1280px; margin:8px auto 0; }}
body.notatki .notatka {{ display:block; }}

/* --- ekran: skalowanie do okna --- */
@media screen {{
  body {{ padding:28px 0 60px; }}
  .scena {{ width:1280px; transform-origin:top center; margin:0 auto; }}
  .pasek {{ position:fixed; left:0; right:0; bottom:0; height:38px; background:var(--granat);
           color:#cbd5e1; display:flex; align-items:center; justify-content:center; gap:22px;
           font-size:13px; z-index:10; }}
  .pasek b {{ color:#fff; }}
  .pasek kbd {{ background:rgba(255,255,255,.14); border-radius:4px; padding:2px 6px;
               font-family:inherit; font-size:12px; }}
  body.pokaz {{ background:#0f172a; padding:0; }}
  body.pokaz .scena {{ display:flex; align-items:center; justify-content:center;
                      height:100vh; width:100vw; }}
  body.pokaz .slajd {{ display:none; }}
  body.pokaz .slajd.aktywny {{ display:flex; }}
  body.pokaz .slajd + .slajd {{ margin-top:0; }}
  body.pokaz .notatka {{ display:none; }}
}}

/* --- druk: jeden slajd = jedna strona, bez marginesu --- */
@page {{ size:338.667mm 190.5mm; margin:0; }}
@media print {{
  body {{ background:#fff; padding:0; }}
  .scena {{ transform:none !important; width:auto; }}
  .slajd {{ break-after:page; page-break-after:always; margin:0 !important; box-shadow:none; }}
  .slajd:last-child {{ break-after:auto; page-break-after:auto; }}
  .notatka, .pasek {{ display:none !important; }}
}}
"""

SKRYPT = """
(() => {
  const slajdy = [...document.querySelectorAll('.slajd')];
  let i = 0, pokaz = false;

  // Skalowanie sceny do szerokości okna — slajd ma stały rozmiar 1280x720
  const skaluj = () => {
    const scena = document.querySelector('.scena');
    if (pokaz) {
      const s = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
      scena.style.transform = `scale(${s})`;
      scena.style.width = '1280px';
      scena.style.height = '720px';
    } else {
      const s = Math.min(1, (window.innerWidth - 48) / 1280);
      scena.style.transform = `scale(${s})`;
      scena.style.height = (scena.scrollHeight * s) + 'px';
    }
  };

  const pokazSlajd = (n) => {
    i = Math.max(0, Math.min(slajdy.length - 1, n));
    slajdy.forEach((s, k) => s.classList.toggle('aktywny', k === i));
    licznik.textContent = `${i + 1} / ${slajdy.length}`;
    if (!pokaz) slajdy[i].scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const pasek = document.querySelector('.pasek');
  const licznik = document.getElementById('licznik');

  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') { pokazSlajd(i + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { pokazSlajd(i - 1); e.preventDefault(); }
    else if (e.key === 'Home') pokazSlajd(0);
    else if (e.key === 'End') pokazSlajd(slajdy.length - 1);
    else if (e.key.toLowerCase() === 'n') document.body.classList.toggle('notatki');
    else if (e.key.toLowerCase() === 'p') {
      pokaz = !pokaz;
      document.body.classList.toggle('pokaz', pokaz);
      pokazSlajd(i); skaluj();
    }
  });

  window.addEventListener('resize', skaluj);
  window.addEventListener('load', skaluj);
  skaluj(); pokazSlajd(0);
})();
"""


def render():
    html = []
    for numer, s in enumerate(SLAJDY, start=1):
        if s.get("typ") == "okladka":
            ciało = (f'<div class="kreska"></div><h1>{s["tytul"]}</h1>'
                     f'<div class="obietnica">{s["podtytul"]}</div>'
                     f'<div class="meta"><b>Polmedi Group sp. z o.o.</b> · Poznań<br>'
                     f'Wersja aplikacji {WERSJA} · {DATA}</div>')
            html.append(f'<div class="slajd okladka">{ciało}<div class="numer">{numer}</div></div>')
        else:
            src = obraz(s["obraz"]) if s.get("obraz") else None
            klasy = "tresc" + (" z-obrazem" if src else "") + (" obraz-maly" if s.get("obraz_maly") else "")
            if src:
                ciało = (f'<div class="{klasy}"><div class="kolumna">{s["tresc"]}</div>'
                         f'<figure><img src="{src}" alt=""></figure></div>')
            else:
                ciało = f'<div class="{klasy}">{s["tresc"]}</div>'
            stopka = f'<div class="stopka-slajdu">{s["stopka"]}</div>' if s.get("stopka") else ""
            if s.get("puenta"):
                stopka += f'<div class="puenta">{s["puenta"]}</div>' 
            html.append(
                f'<div class="slajd"><h2>{s["tytul"]}</h2>{ciało}{stopka}'
                f'<div class="marka">ZCO Document Management</div>'
                f'<div class="numer">{numer}</div></div>'
            )
        if s.get("notatka"):
            html.append(f'<div class="notatka"><b>Mówione:</b> {s["notatka"]}</div>')

    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<title>ZCO Document Management — prezentacja</title>
<style>{STYL}</style></head>
<body>
<div class="scena">{''.join(html)}</div>
<div class="pasek">
  <span><b id="licznik">1 / {len(SLAJDY)}</b></span>
  <span><kbd>→</kbd> <kbd>←</kbd> slajdy</span>
  <span><kbd>P</kbd> tryb pokazu</span>
  <span><kbd>N</kbd> notatki prelegenta</span>
</div>
<script>{SKRYPT}</script>
</body></html>"""


def do_pdf(html_path, pdf_path, limit_sekund=300):
    """Wydruk przez Edge headless. Uwaga: właściwa flaga to --print-to-pdf-no-header
    (wariant --no-pdf-header-footer Edge po cichu ignoruje), a proces kończy się
    ZANIM dopisze plik — czekamy, aż PDF przestanie rosnąć."""
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    profil = tempfile.mkdtemp(prefix="prez_pdf_")
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={profil}",
         "--no-pdf-header-footer", "--print-to-pdf-no-header",
         f"--print-to-pdf={pdf_path}", "--virtual-time-budget=20000",
         f"file:///{html_path.replace(os.sep, '/')}"],
        capture_output=True, timeout=limit_sekund,
    )
    poprzedni, stabilne = -1, 0
    for _ in range(int(limit_sekund * 2)):
        if os.path.exists(pdf_path):
            rozmiar = os.path.getsize(pdf_path)
            stabilne = stabilne + 1 if rozmiar == poprzedni and rozmiar > 0 else 0
            poprzedni = rozmiar
            if stabilne >= 3:
                return True
        time.sleep(0.5)
    return os.path.exists(pdf_path)


def main():
    html_path = os.path.join(KATALOG, "ZCO-DM-prezentacja.html")
    pdf_path = os.path.join(KATALOG, "ZCO-DM-prezentacja.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render())
    ok = do_pdf(html_path, pdf_path)
    print(f"ZCO-DM-prezentacja: {len(SLAJDY)} slajdów, "
          f"{os.path.getsize(html_path)//1024} KB HTML, "
          f"{(os.path.getsize(pdf_path)//1024) if ok else 0} KB PDF")


if __name__ == "__main__":
    main()
