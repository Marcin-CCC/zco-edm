"""Prezentacja sprzedażowa EDMund — wersja uniwersalna, dla dowolnego klienta.

Różnice wobec wydania dla jednego klienta:
  * nazwa systemu EDMund („czyli mów mi Mundek”) zamiast nazwy wdrożenia,
  * ani jednej nazwy własnej klienta — przykłady dotyczą typowych działów firmy,
  * kolory marki Polmedi ze strony polmedi.com,
  * zamiast zrzutów ekranu z bazy klienta — makiety rysowane wektorowo, żeby nie
    pokazywać cudzych dokumentów.

Kolory i ich rola (sprawdzone walidatorem palet, tryb jasny):
  #2448c8  niebieski marki — znaczniki, panele, akcenty,
  #09afaf  turkus marki — gradienty i akcenty na ciemnym tle; na białym ma kontrast
           2,64:1, czyli poniżej progu 3:1 dla elementów graficznych,
  #0a9a9a  turkus przyciemniony — znaczniki na białym (kontrast ponad 3:1, ten sam odcień);
           para #2448c8/#0a9a9a przechodzi komplet sześciu testów (ΔE 22,3 przy zaburzeniach
           widzenia barw),
  #465050  kolor pisma ze strony polmedi.com.
Każdy znacznik ma podpis wprost przy sobie, więc kolor nigdy nie niesie znaczenia sam.

Slajd ma stały rozmiar 1280×720 px (16:9); w druku strona to 338,667×190,5 mm, czyli te
same wymiary przy 96 dpi — jeden slajd na jedną stronę PDF.

    python generuj.py
"""
import base64
import os
import subprocess
import tempfile
import time

KATALOG = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

NAZWA = "EDMund"
PODTYTUL_NAZWY = "Enterprise Document Management — czyli mów mi Mundek"
DATA = "1 sierpnia 2026"
WYKONAWCA = "Polmedi Group sp. z o.o., Poznań"

NIEBIESKI = "#2448c8"
TURKUS = "#09afaf"
TURKUS_CIEMNY = "#0a9a9a"
GRADIENT = f"linear-gradient(90deg, {NIEBIESKI} 0%, {TURKUS} 100%)"
TEKST = "#465050"
SZARY = "#7b8585"
LINIA = "#e2e8f0"
TLO = "#f7fafb"


def logo_data_uri():
    plik = os.path.join(KATALOG, "polmedi-group.png")
    if not os.path.exists(plik):
        return None
    with open(plik, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def punkty(*tresc):
    return "<ul class='punkty'>" + "".join(f"<li>{t}</li>" for t in tresc) + "</ul>"


# ---------------------------------------------------------------- dane infografik

KROKI_SCIEZKI = [
    ("1", "Pytanie", "zwykłym językiem, np. „jak rozliczyć delegację?”"),
    ("2", "Wyszukanie", "system znajduje fragmenty w Waszych plikach"),
    ("3", "Odpowiedź", "zbudowana wyłącznie z tych fragmentów"),
    ("4", "Dowód", "numer przy zdaniu prowadzi do dokumentu i strony"),
]
KAFELKI_LICZB = [
    ("128 GB", "pamięci dla modelu", "jedno urządzenie obsługuje całą firmę"),
    ("4 TB", "na dokumenty", "setki tysięcy plików biurowych"),
    ("~1 s", "do pierwszego słowa odpowiedzi", "cała odpowiedź gotowa w ok. 15 s"),
]
CZASY = [
    ("Czas do rozpoczęcia odpowiedzi", 1, "ok. 1 s"),
    ("Czas utworzenia całej odpowiedzi", 15, "ok. 15 s"),
    ("Przygotowanie dokumentu", 60, "średnio ok. 60 s"),
]
ETAPY_WDROZENIA = [
    ("Tydzień 1", "Instalacja i uruchomienie", "urządzenie w serwerowni, konta, uprawnienia"),
    ("Tydzień 2", "Wasze dokumenty i wzorce", "wgrywamy pierwszą partię, układamy schematy pism"),
    ("Tydzień 3", "Szkolenia i start", "20 min dla użytkownika, 2 h dla administratora"),
]
DZIALY = [
    ("Kadry i płace", "regulaminy, wnioski, świadczenia pracownicze"),
    ("Jakość i audyty", "procedury, instrukcje, wersje obowiązujące"),
    ("Zespoły operacyjne", "instrukcje stanowiskowe i procedury wewnętrzne"),
    ("Administracja i zakupy", "umowy, zarządzenia, dokumentacja przetargowa"),
    ("BHP · RODO · IT", "polityki i instrukcje wewnętrzne"),
    ("Branże", "ochrona zdrowia, uczelnie, urzędy, kancelarie, produkcja"),
]
CENNIK = [
    ("Sprzęt: serwer AI z 128 GB pamięci i dyskiem 4 TB", "20 000 zł"),
    ("Dostawa i wdrożenie oprogramowania", "25 000 zł"),
    ("Wsparcie i rozwój", "1 000 zł / mies."),
]
OSOBY_KONTAKT = [
    ("Piotr Piątek", "wyceny, umowa", "501 674 303"),
    ("Marcin Cieślak", "sprawy techniczne", "602 220 693"),
]
WARSTWY_SERWEROWNI = [
    ("Aplikacja", "przeglądarka pracownika"),
    ("Model językowy", "działa na Waszym urządzeniu"),
    ("Dokumenty i indeks", "dysk w serwerowni"),
]


# ---------------------------------------------------------------- infografiki

def graf_bezpieczenstwo():
    kafle = "".join(
        f"<div class='kafel'><b>{n}</b><span>{o}</span></div>" for n, o in WARSTWY_SERWEROWNI)
    return f"""
<div class="graf-bezp">
  <div class="budynek">
    <div class="budynek-etykieta">Wasza serwerownia</div>
    <div class="kafle">{kafle}</div>
  </div>
  <div class="mur"><div class="mur-linia"></div>
    <div class="mur-podpis">brak połączenia<br>z usługami zewnętrznymi</div></div>
  <div class="chmura"><b>Internet</b>
    <span>nie wychodzi tu żaden dokument,<br>fragment ani pytanie</span></div>
</div>"""


def graf_sciezka():
    kafle = "".join(
        f"<div class='krok'><div class='krok-numer'>{n}</div><b>{t}</b><span>{o}</span></div>"
        + ("<div class='strzalka'>→</div>" if n != "4" else "")
        for n, t, o in KROKI_SCIEZKI)
    return f"<div class='graf-sciezka'>{kafle}</div>"


def graf_liczby():
    kafle = "".join(
        f"<div class='liczba'><div class='liczba-duza'>{d}</div>"
        f"<div class='liczba-opis'>{o}</div><div class='liczba-nota'>{n}</div></div>"
        for d, o, n in KAFELKI_LICZB)
    wiersze = "".join(
        f"<div class='slupek-wiersz'><span class='slupek-nazwa'>{nazwa}</span>"
        f"<span class='slupek-tor'><span class='slupek' style='width:{sek / 60 * 100:.2f}%;"
        f"background:{TURKUS_CIEMNY if sek < 60 else NIEBIESKI}'></span></span>"
        f"<span class='slupek-wartosc'>{etykieta}</span></div>"
        for nazwa, sek, etykieta in CZASY)
    return f"""
<div class='graf-liczby'>{kafle}</div>
<div class='slupki'>
  <div class='slupki-tytul'>Ile to trwa w praktyce</div>
  {wiersze}
  <div class='slupki-nota'>Długość słupka odpowiada czasowi. Pomiary z działającego wdrożenia;
    przygotowanie dokumentu odbywa się raz, w tle, przy wgraniu pliku.</div>
</div>"""


def graf_harmonogram():
    return "<div class='harmonogram'>" + "".join(
        f"<div class='etap'><div class='etap-kropka'></div><div class='etap-tydzien'>{t}</div>"
        f"<b>{n}</b><span>{o}</span></div>" for t, n, o in ETAPY_WDROZENIA) + "</div>"


def graf_zastosowania():
    return "<div class='siatka-dzialow'>" + "".join(
        f"<div class='dzial'><b>{n}</b><span>{o}</span></div>" for n, o in DZIALY) + "</div>"


def graf_cennik():
    wiersze = "".join(f"<tr><td>{n}</td><td class='kwota'>{k}</td></tr>" for n, k in CENNIK)
    return f"""
<table class='cennik'>
  <tr><th>Pozycja</th><th class='kwota'>Netto</th></tr>
  {wiersze}
  <tr class='suma'><td>Rok pierwszy łącznie</td><td class='kwota'>57 000 zł</td></tr>
</table>
<div class='cennik-nota'>
  <div><b>Bez opłat za użytkownika</b> i bez opłat za liczbę dokumentów.</div>
  <div><b>Sprzęt zostaje Wasz</b> — nie płacicie abonamentu za dostęp do własnych danych.</div>
  <div>Trzy lata użytkowania: <b>81 000 zł netto</b>.</div>
</div>"""


def graf_kontakt():
    karty = []
    for imie, rola, telefon in OSOBY_KONTAKT:
        czlony = imie.split()
        karty.append(
            f"<div class='kontakt'><div class='kontakt-inicjaly'>"
            f"{(czlony[0][0] + czlony[-1][0]).upper()}</div>"
            f"<div class='kontakt-dane'><b>{imie}</b><span class='kontakt-rola'>{rola}</span>"
            f"<span class='kontakt-tel'>tel. {telefon}</span></div></div>")
    return "<div class='kontakty'>" + "".join(karty) + "</div>"


# ---------------------------------------------------------------- makiety ekranów

def makieta_pliki():
    """Makieta eksploratora — rysowana, nie zrzut: nie pokazujemy cudzych dokumentów."""
    foldery = ["Kadry i płace", "Procedury", "Umowy", "BHP", "Jakość i audyty", "Szkolenia"]
    kafle = "".join(
        f"<div class='m-folder'><div class='m-ikona'></div><b>{f}</b>"
        f"<span>dokumentów: {8 + i * 3}</span></div>" for i, f in enumerate(foldery))
    return f"""
<div class='makieta'>
  <div class='m-belka'><span class='m-logo'>{NAZWA}</span></div>
  <div class='m-tresc'>
    <div class='m-menu'><span class='m-akt'>Pliki</span><span>Baza wiedzy</span><span>Profil</span></div>
    <div class='m-panel'><div class='m-tytul'>Eksplorator plików</div>
      <div class='m-foldery'>{kafle}</div></div>
  </div>
</div>"""


def makieta_czat():
    return f"""
<div class='makieta'>
  <div class='m-belka'><span class='m-logo'>{NAZWA}</span></div>
  <div class='m-tresc'>
    <div class='m-menu'><span>Pliki</span><span class='m-akt'>Baza wiedzy</span><span>Profil</span></div>
    <div class='m-panel'>
      <div class='m-pytanie'>jak rozliczyć delegację?</div>
      <div class='m-odpowiedz'>Rozliczenie podróży służbowej składa się w ciągu 3 dni roboczych
        od powrotu, na formularzu „polecenie wyjazdu służbowego” <span class='m-zrodlo'>1</span>.
        Do rozliczenia dołącza się bilety i rachunki <span class='m-zrodlo'>2</span>.
        <div class='m-zrodla'>Dokumenty użyte w odpowiedzi:
          <div><span class='m-zrodlo'>1</span> Regulamin podróży służbowych.pdf (str. 3)</div>
          <div><span class='m-zrodlo'>2</span> Polecenie wyjazdu służbowego.docx (str. 1)</div>
        </div>
      </div>
      <div class='m-pytanie'>a kto to zatwierdza?</div>
    </div>
  </div>
</div>"""


# ---------------------------------------------------------------- slajdy

SLAJDY = [
    {
        "typ": "okladka",
        "tytul": NAZWA,
        "podtytul": "Pytasz jak człowieka. Odpowiada z Waszych dokumentów.<br>"
                    "Nic nie wychodzi poza Waszą sieć.",
        "notatka": "EDMund to skrót od Enterprise Document Management — stąd Mundek. "
                   "Trzy rzeczy do zapamiętania: odpowiedzi wskazują dokument źródłowy, "
                   "dane nie opuszczają firmy, obsługa to wpisanie pytania.",
    },
    {
        "tytul": "Problem, który znają wszyscy",
        "puenta": "Wiedza jest w dokumentach. Problemem jest droga do niej.",
        "tresc": punkty(
            "Dokument jest — tylko nie wiadomo, w którym folderze i <b>która wersja obowiązuje</b>",
            "Nowa osoba pyta koleżankę zamiast szukać w regulaminie",
            "Ta sama odpowiedź udzielana dziesiątki razy przez kadry i dział jakości",
            "Przy audycie i kontroli liczy się <b>czas dotarcia do właściwego zapisu</b>",
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
        "makieta": makieta_pliki(),
        "notatka": "Trzy drogi do dokumentu: przeglądanie, pytanie o treść, wyszukiwanie po opisie.",
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
        "notatka": "Jak cytowanie w publikacji — każde twierdzenie sprawdzalne w dwie sekundy.",
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
            "Trzy ekrany: <b>Dashboard</b>, <b>Pliki</b>, <b>Baza wiedzy</b>. Administracja tylko "
            "dla administratora",
            "Pytanie potoczne działa: „delegacja” znajdzie „podróż służbową”, „L4” — „zwolnienie lekarskie”",
            "Wystarczy sama nazwa dokumentu, żeby dostać jego opis i odnośnik",
            "<b>Szkolenie pracownika: 20 minut.</b> Instrukcja w aplikacji, pod przyciskiem Pomoc",
        ),
        "makieta": makieta_czat(),
        "notatka": "Sprawdzianem jest osoba, która nie chce uczyć się nowego programu.",
    },
    {
        "tytul": "Gdzie to pracuje",
        "puenta": "Kolejny dział to wgranie dokumentów, a nie nowe wdrożenie.",
        "tresc": graf_zastosowania() + punkty(
            "Zaczynamy zwykle od kadr — tam pytania powtarzają się najczęściej, efekt widać "
            "w pierwszym tygodniu",
            "Rozszerzenie na kolejny dział to wgranie dokumentów i nadanie uprawnień",
        ),
        "notatka": "System sprawdzi się wszędzie tam, gdzie jest duży zasób dokumentów wewnętrznych.",
    },
    {
        "tytul": "Nasza rola: wdrożenie i wsparcie",
        "puenta": "Przychodzimy z Waszymi dokumentami już w środku.",
        "tresc": graf_harmonogram() + punkty(
            "<b>Nie zostawiamy pustego systemu</b> — pierwsza partia dokumentów wgrana i sprawdzona "
            "przez nas",
            "<b>Wzorce pod Wasze pisma</b> — system sam wyciąga numer, datę i osobę zatwierdzającą",
            "<b>Wsparcie miesięczne</b> — aktualizacje, opieka nad jakością odpowiedzi, nowe rodzaje "
            "dokumentów",
            "<b>Kierunek rozwoju</b>: powiązania między dokumentami i wersja obowiązująca, podgląd PDF "
            "na cytowanej stronie, logowanie kontem domenowym, integracja z systemami dziedzinowymi",
        ),
        "notatka": "Najczęstszy powód, dla którego takie systemy umierają, to pusty start. "
                   "Ostatni punkt to plan, nie stan obecny.",
    },
    {
        "tytul": "Warunki i następny krok",
        "puenta": "Następny krok: dwutygodniowe uruchomienie próbne na Waszych dokumentach "
                  "— u Was, bez zobowiązania.",
        "tresc": graf_cennik(),
        "notatka": "Nie proszę o decyzję zakupową, tylko o test na własnych dokumentach.",
    },
    {
        "tytul": "Zapraszamy do kontaktu",
        "puenta": "Jesteśmy tu dla Was.",
        "tresc": "<div class='kontakt-wstep'>Czekają na Was:</div>" + graf_kontakt()
                 + "<div class='kontakt-firma'><b>Polmedi Group sp. z o.o.</b> · Poznań"
                   "<span>polmedi.com</span></div>",
        "notatka": "Do Piotra w sprawie wyceny i umowy, do mnie — gdy pytanie jest techniczne.",
    },
]

STYL = f"""
:root {{
  --niebieski:{NIEBIESKI}; --turkus:{TURKUS}; --turkus-ciemny:{TURKUS_CIEMNY};
  --tekst:{TEKST}; --szary:{SZARY}; --linia:{LINIA}; --tlo:{TLO};
  --gradient:{GRADIENT};
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:"Segoe UI",Arial,sans-serif; color:var(--tekst); background:#e8eef2; }}

.slajd {{ width:1280px; height:720px; background:#fff; position:relative; overflow:hidden;
         display:flex; flex-direction:column; padding:56px 64px 48px; }}
.slajd + .slajd {{ margin-top:24px; }}
.slajd h2 {{ font-size:40px; line-height:1.15; color:var(--niebieski); margin-bottom:8px; }}
.slajd h2::after {{ content:""; display:block; width:96px; height:5px; background:var(--gradient);
                   border-radius:3px; margin-top:14px; }}
.tresc {{ flex:1; display:flex; flex-direction:column; gap:20px; margin-top:26px; min-height:0; }}
.tresc.z-makieta {{ flex-direction:row; align-items:flex-start; gap:36px; }}
.tresc.z-makieta .kolumna {{ flex:1 1 54%; min-width:0; }}
.tresc.z-makieta .makieta-slot {{ flex:1 1 46%; min-width:0; }}

ul.punkty {{ list-style:none; }}
ul.punkty li {{ position:relative; padding-left:32px; margin-bottom:20px; font-size:23px;
               line-height:1.45; }}
ul.punkty li::before {{ content:""; position:absolute; left:4px; top:13px; width:11px; height:11px;
                       border-radius:50%; background:var(--turkus-ciemny); }}

/* --- makieta ekranu (rysowana, nie zrzut) --- */
.makieta {{ border:1px solid var(--linia); border-radius:10px; overflow:hidden;
           box-shadow:0 10px 26px rgba(36,72,200,.10); background:#fff; }}
.m-belka {{ background:var(--gradient); padding:10px 14px; }}
.m-logo {{ color:#fff; font-weight:700; font-size:15px; letter-spacing:.02em; }}
.m-tresc {{ display:flex; min-height:250px; }}
.m-menu {{ width:110px; background:#f1f5f9; padding:12px 10px; display:flex; flex-direction:column;
          gap:8px; font-size:12px; color:var(--szary); }}
.m-menu .m-akt {{ background:var(--niebieski); color:#fff; border-radius:5px; padding:4px 8px;
                 margin:-4px -8px; }}
.m-panel {{ flex:1; padding:14px 16px; }}
.m-tytul {{ font-size:15px; font-weight:600; color:var(--niebieski); margin-bottom:10px; }}
.m-foldery {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.m-folder {{ border:1px solid var(--linia); border-radius:7px; padding:9px 10px; background:var(--tlo); }}
.m-ikona {{ width:22px; height:16px; border-radius:3px; background:var(--turkus); margin-bottom:6px;
           opacity:.85; }}
.m-folder b {{ display:block; font-size:11.5px; color:var(--tekst); line-height:1.25; }}
.m-folder span {{ font-size:10px; color:var(--szary); }}
.m-pytanie {{ background:var(--niebieski); color:#fff; font-size:12px; border-radius:9px;
             padding:7px 11px; margin:0 0 10px auto; width:max-content; max-width:75%; }}
.m-odpowiedz {{ background:var(--tlo); border:1px solid var(--linia); border-radius:9px;
               padding:10px 12px; font-size:12px; line-height:1.5; margin-bottom:10px; }}
.m-zrodlo {{ display:inline-block; min-width:15px; text-align:center; background:#dbeafe;
            color:var(--niebieski); border-radius:4px; font-size:10px; font-weight:700;
            padding:0 3px; vertical-align:super; }}
.m-zrodla {{ margin-top:9px; padding-top:8px; border-top:1px solid var(--linia); font-size:10.5px;
            color:var(--szary); }}
.m-zrodla div {{ margin-top:3px; color:var(--niebieski); }}

/* --- infografiki --- */
.graf-bezp {{ display:flex; align-items:stretch; }}
.budynek {{ flex:1; background:var(--niebieski); border-radius:12px; padding:18px 20px 20px; }}
.budynek-etykieta {{ color:var(--turkus); font-size:15px; font-weight:700; letter-spacing:.06em;
                    text-transform:uppercase; margin-bottom:14px; }}
.kafle {{ display:flex; gap:12px; }}
.kafel {{ flex:1; background:rgba(255,255,255,.10); border-radius:9px; padding:16px 18px; color:#fff; }}
.kafel b {{ display:block; font-size:18px; margin-bottom:4px; }}
.kafel span {{ font-size:14px; color:#dbe4f7; line-height:1.35; }}
.mur {{ width:96px; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.mur-linia {{ width:0; height:96px; border-left:5px dashed var(--turkus-ciemny); }}
.mur-podpis {{ font-size:12.5px; color:var(--turkus-ciemny); font-weight:600; text-align:center;
              margin-top:8px; line-height:1.3; }}
.chmura {{ width:250px; border:2px solid #cbd5e1; background:var(--tlo); border-radius:12px;
          padding:16px; text-align:center; display:flex; flex-direction:column; justify-content:center; }}
.chmura b {{ font-size:17px; color:var(--niebieski); margin-bottom:5px; }}
.chmura span {{ font-size:13px; color:var(--tekst); line-height:1.4; }}

.graf-sciezka {{ display:flex; align-items:stretch; gap:8px; }}
.krok {{ flex:1; background:var(--tlo); border:1px solid var(--linia); border-radius:10px;
        padding:16px 18px; }}
.krok-numer {{ width:26px; height:26px; border-radius:50%; background:var(--turkus-ciemny); color:#fff;
              font-size:14px; font-weight:700; display:flex; align-items:center; justify-content:center;
              margin-bottom:8px; }}
.krok b {{ display:block; font-size:19px; color:var(--niebieski); margin-bottom:3px; }}
.krok span {{ font-size:14.5px; color:var(--szary); line-height:1.35; }}
.strzalka {{ align-self:center; color:var(--turkus-ciemny); font-size:22px; }}

.graf-liczby {{ display:flex; gap:18px; }}
.liczba {{ flex:1; border:1px solid var(--linia); border-radius:12px; padding:26px 24px;
          background:var(--tlo); }}
.liczba-duza {{ font-size:58px; font-weight:700; color:var(--niebieski); line-height:1; }}
.liczba-opis {{ font-size:19px; color:var(--tekst); margin-top:6px; }}
.liczba-nota {{ font-size:14px; color:var(--szary); margin-top:6px; line-height:1.35; }}
.slupki {{ border-top:1px solid var(--linia); padding-top:18px; }}
.slupki-tytul {{ font-size:15px; font-weight:600; color:var(--niebieski); margin-bottom:12px; }}
.slupek-wiersz {{ display:flex; align-items:center; gap:14px; margin-bottom:10px; }}
.slupek-nazwa {{ width:300px; font-size:17px; color:var(--tekst); }}
.slupek-tor {{ flex:0 0 620px; height:20px; }}
.slupek {{ display:block; height:100%; border-radius:4px; }}
.slupek-wartosc {{ font-size:17px; font-weight:600; color:var(--tekst); }}
.slupki-nota {{ font-size:12.5px; color:var(--szary); margin-top:4px; line-height:1.4; }}

.harmonogram {{ display:flex; gap:14px; }}
.etap {{ flex:1; border-left:3px solid var(--turkus); padding:4px 16px 8px; position:relative; }}
.etap-kropka {{ position:absolute; left:-9px; top:6px; width:15px; height:15px; border-radius:50%;
               background:var(--turkus-ciemny); border:3px solid #fff; }}
.etap-tydzien {{ font-size:13px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
                color:var(--turkus-ciemny); margin-bottom:4px; }}
.etap b {{ display:block; font-size:21px; color:var(--niebieski); margin-bottom:4px; }}
.etap span {{ font-size:15.5px; color:var(--szary); line-height:1.4; }}

.siatka-dzialow {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.dzial {{ border:1px solid var(--linia); border-radius:10px; padding:18px 20px; background:var(--tlo); }}
.dzial b {{ display:block; font-size:20px; color:var(--niebieski); margin-bottom:4px; }}
.dzial span {{ font-size:15px; color:var(--szary); line-height:1.35; }}

table.cennik {{ width:100%; border-collapse:collapse; font-size:20px; }}
table.cennik th {{ text-align:left; font-size:14px; letter-spacing:.06em; text-transform:uppercase;
                  color:var(--szary); padding:0 0 10px; border-bottom:2px solid var(--linia); }}
table.cennik th.kwota, table.cennik td.kwota {{ text-align:right; white-space:nowrap; }}
table.cennik td {{ padding:14px 0; border-bottom:1px solid var(--linia); }}
table.cennik tr.suma td {{ font-weight:700; color:var(--niebieski); font-size:23px; border-bottom:none;
                          padding-top:18px; }}
.cennik-nota {{ display:flex; gap:28px; margin-top:20px; }}
.cennik-nota div {{ flex:1; font-size:15px; line-height:1.45; border-left:3px solid var(--turkus);
                   padding-left:12px; }}

.kontakt-wstep {{ font-size:23px; margin-bottom:6px; }}
.kontakty {{ display:flex; gap:28px; }}
.kontakt {{ flex:1; display:flex; align-items:center; gap:22px; background:var(--tlo);
           border:1px solid var(--linia); border-left:6px solid var(--turkus-ciemny);
           border-radius:12px; padding:34px 30px; }}
.kontakt-inicjaly {{ width:74px; height:74px; flex:0 0 74px; border-radius:50%;
                    background:var(--gradient); color:#fff; font-size:27px; font-weight:700;
                    display:flex; align-items:center; justify-content:center; }}
.kontakt-dane {{ display:flex; flex-direction:column; gap:3px; min-width:0; }}
.kontakt-dane b {{ font-size:26px; color:var(--niebieski); line-height:1.2; }}
.kontakt-rola {{ font-size:17px; color:var(--szary); }}
.kontakt-tel {{ font-size:26px; font-weight:600; color:var(--turkus-ciemny); margin-top:6px;
               white-space:nowrap; }}
.kontakt-firma {{ margin-top:30px; padding-top:22px; border-top:1px solid var(--linia);
                 display:flex; align-items:baseline; gap:16px; font-size:19px; }}
.kontakt-firma b {{ color:var(--niebieski); }}
.kontakt-firma span {{ color:var(--turkus-ciemny); font-weight:600; }}

.puenta {{ margin-top:auto; margin-bottom:6px; background:var(--niebieski); color:#fff;
          border-radius:10px; padding:16px 22px; font-size:22px; font-weight:600; line-height:1.35;
          border-left:6px solid var(--turkus); }}

.slajd.okladka {{ background:var(--niebieski); color:#fff; justify-content:center; }}
.slajd.okladka::before {{ content:""; position:absolute; inset:0;
    background:radial-gradient(circle at 88% 18%, rgba(9,175,175,.55) 0%, rgba(9,175,175,0) 46%); }}
.slajd.okladka > * {{ position:relative; }}
.slajd.okladka .numer {{ position:absolute; color:#8fa4d8; }}
.slajd.okladka .kreska {{ width:120px; height:6px; background:var(--gradient); border-radius:3px;
                         margin-bottom:34px; }}
.slajd.okladka h1 {{ font-size:76px; line-height:1.05; margin-bottom:10px; letter-spacing:-.01em; }}
.slajd.okladka .rozwiniecie {{ font-size:20px; color:#c7f3f3; margin-bottom:26px; }}
.slajd.okladka .obietnica {{ font-size:26px; line-height:1.5; color:#fff; max-width:860px; }}
.slajd.okladka .meta {{ position:absolute; left:64px; bottom:48px; font-size:16px; color:#b9c6ea; }}
.slajd.okladka .meta b {{ color:#eaf0ff; }}
.slajd.okladka .logo {{ position:absolute; right:64px; bottom:44px; height:40px; opacity:.95;
                       background:#fff; border-radius:8px; padding:6px 10px; }}

.marka {{ position:absolute; left:64px; bottom:22px; font-size:13px; color:#9aa5a5; }}
.numer {{ position:absolute; right:32px; bottom:22px; font-size:13px; color:#9aa5a5; }}
.logo-rog {{ position:absolute; right:56px; top:44px; height:26px; opacity:.9; }}

.notatka {{ display:none; background:#fffbeb; border:1px solid #fde68a; border-radius:8px;
           padding:12px 16px; font-size:15px; color:#78350f; width:1280px; margin:8px auto 0; }}
body.notatki .notatka {{ display:block; }}

@media screen {{
  body {{ padding:28px 0 60px; }}
  .scena {{ width:1280px; transform-origin:top center; margin:0 auto; }}
  .pasek {{ position:fixed; left:0; right:0; bottom:0; height:38px; background:var(--niebieski);
           color:#dbe4f7; display:flex; align-items:center; justify-content:center; gap:22px;
           font-size:13px; z-index:10; }}
  .pasek b {{ color:#fff; }}
  .pasek kbd {{ background:rgba(255,255,255,.16); border-radius:4px; padding:2px 6px;
               font-family:inherit; font-size:12px; }}
  body.pokaz {{ background:#0b1220; padding:0; }}
  body.pokaz .scena {{ display:flex; align-items:center; justify-content:center;
                      height:100vh; width:100vw; }}
  body.pokaz .slajd {{ display:none; }}
  body.pokaz .slajd.aktywny {{ display:flex; }}
  body.pokaz .slajd + .slajd {{ margin-top:0; }}
  body.pokaz .notatka {{ display:none; }}
}}

@page {{ size:338.667mm 190.5mm; margin:0; }}
@media print {{
  body {{ background:#fff; padding:0; }}
  .scena {{ transform:none !important; width:auto; }}
  .slajd {{ break-after:page; page-break-after:always; margin:0 !important; }}
  .slajd:last-child {{ break-after:auto; page-break-after:auto; }}
  .notatka, .pasek {{ display:none !important; }}
}}
"""

SKRYPT = """
(() => {
  const slajdy = [...document.querySelectorAll('.slajd')];
  let i = 0, pokaz = false;
  const licznik = document.getElementById('licznik');
  const skaluj = () => {
    const scena = document.querySelector('.scena');
    if (pokaz) {
      const s = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
      scena.style.transform = `scale(${s})`;
      scena.style.width = '1280px'; scena.style.height = '720px';
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
  document.addEventListener('keydown', (e) => {
    if (['ArrowRight', 'PageDown', ' '].includes(e.key)) { pokazSlajd(i + 1); e.preventDefault(); }
    else if (['ArrowLeft', 'PageUp'].includes(e.key)) { pokazSlajd(i - 1); e.preventDefault(); }
    else if (e.key === 'Home') pokazSlajd(0);
    else if (e.key === 'End') pokazSlajd(slajdy.length - 1);
    else if (e.key.toLowerCase() === 'n') document.body.classList.toggle('notatki');
    else if (e.key.toLowerCase() === 'p') {
      pokaz = !pokaz; document.body.classList.toggle('pokaz', pokaz); pokazSlajd(i); skaluj();
    }
  });
  window.addEventListener('resize', skaluj);
  window.addEventListener('load', skaluj);
  skaluj(); pokazSlajd(0);
})();
"""


def render():
    logo = logo_data_uri()
    html = []
    for numer, s in enumerate(SLAJDY, start=1):
        if s.get("typ") == "okladka":
            znak = f'<img class="logo" src="{logo}" alt="Polmedi Group">' if logo else ""
            html.append(
                f'<div class="slajd okladka"><div class="kreska"></div>'
                f'<h1>{s["tytul"]}</h1>'
                f'<div class="rozwiniecie">{PODTYTUL_NAZWY}</div>'
                f'<div class="obietnica">{s["podtytul"]}</div>'
                f'<div class="meta"><b>{WYKONAWCA}</b><br>{DATA}</div>{znak}'
                f'<div class="numer">{numer}</div></div>')
        else:
            znak = f'<img class="logo-rog" src="{logo}" alt="">' if logo else ""
            if s.get("makieta"):
                ciało = (f'<div class="tresc z-makieta"><div class="kolumna">{s["tresc"]}</div>'
                         f'<div class="makieta-slot">{s["makieta"]}</div></div>')
            else:
                ciało = f'<div class="tresc">{s["tresc"]}</div>'
            puenta = f'<div class="puenta">{s["puenta"]}</div>' if s.get("puenta") else ""
            html.append(
                f'<div class="slajd">{znak}<h2>{s["tytul"]}</h2>{ciało}{puenta}'
                f'<div class="marka">{NAZWA}</div><div class="numer">{numer}</div></div>')
        if s.get("notatka"):
            html.append(f'<div class="notatka"><b>Mówione:</b> {s["notatka"]}</div>')

    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<title>{NAZWA} — prezentacja</title>
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
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    profil = tempfile.mkdtemp(prefix="edmund_pdf_")
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={profil}",
         "--print-to-pdf-no-header", f"--print-to-pdf={pdf_path}",
         "--virtual-time-budget=20000", f"file:///{html_path.replace(os.sep, '/')}"],
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
    html_path = os.path.join(KATALOG, "EDMund-prezentacja.html")
    pdf_path = os.path.join(KATALOG, "EDMund-prezentacja.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render())
    ok = do_pdf(html_path, pdf_path)
    print(f"EDMund-prezentacja: {len(SLAJDY)} slajdów, {os.path.getsize(html_path)//1024} KB HTML, "
          f"{(os.path.getsize(pdf_path)//1024) if ok else 0} KB PDF")


if __name__ == "__main__":
    main()
