# Prezentacja HiRS — Hospital Information Retrieval System

Dziesięć slajdów 16:9 dla szpitala, bez nazwy konkretnej placówki. Treść odpowiada
wydaniu dla ZCO, ale **ekrany są makietami z wymyślonymi danymi** — prezentacja jedzie
do osób z zewnątrz, więc nie pokazuje ani dokumentów klienta, ani zawartości instancji
demonstracyjnej.

- `HiRS-prezentacja.html` — do pokazywania z laptopa. Klawisze: `→` `←` slajdy,
  `P` tryb pokazu, `N` notatki prelegenta.
- `HiRS-prezentacja.pdf` — do wysłania. Jedna strona = jeden slajd, 338,667 × 190,5 mm.
- `HiRS-prezentacja.pptx` — do samodzielnego poprawiania. Wszystko jest natywnymi
  kształtami i polami tekstowymi (jedyne obrazy to logo i dwie makiety), notatki
  prelegenta w panelu notatek.

```bash
python generuj.py        # HTML + PDF
python makiety_png.py    # makiety ekranów do PPTX (wymaga Edge)
python generuj_pptx.py   # PPTX
```

Treść siedzi w stałych na górze `generuj.py` (`SLAJDY`, `KROKI_SCIEZKI`, `CZASY`,
`CENNIK`, `DZIALY`, `OSOBY_KONTAKT`…) i stamtąd bierze ją **także** generator PPTX —
zmiana tekstu w jednym miejscu przechodzi do wszystkich trzech plików.

## Czym różni się od pozostałych dwóch prezentacji

| | `../prezentacja` | `../prezentacja-uniwersalna` | ten katalog |
|---|---|---|---|
| nazwa | ZCO DM | EDMund | HiRS |
| odbiorca | jeden szpital, z nazwy | dowolna branża | szpital w ogóle |
| ekrany | zrzuty z instancji klienta | makiety, przykłady ogólne | makiety, przykłady szpitalne |
| slajdów | 11 | 11 | **10** |
| kolory | paleta aplikacji | paleta polmedi.com | paleta aplikacji |

Slajdów jest dziesięć, bo warunki handlowe i kontakt stoją razem na ostatnim. Cennik
to trzy wiersze; rozbicie na dwie strony kazałoby wracać do niego przy pytaniu o cenę
na końcu rozmowy.

## Wymyślone dane na makietach

Foldery (`Procedury kliniczne`, `Akredytacja`, `Kadry i płace`, `Zarządzenia dyrektora`,
`BHP i RODO`, `Szkolenia`), liczby dokumentów oraz rozmowa o zgłaszaniu zdarzeń
niepożądanych są **zmyślone i mają takie pozostać**. Przy podmianie na cokolwiek
zaczerpniętego z działającej instancji trzeba pamiętać, że nazwa folderu potrafi
zdradzić więcej, niż się wydaje przy jej wpisywaniu.

## Kolory i ich rola

Paleta aplikacji, sprawdzona walidatorem (tryb jasny, powierzchnia biała):

| Kolor | Rola | Uwaga |
|---|---|---|
| `#1d2a4d` granat | tło paneli, nagłówki | w kodzie pod nazwą `NIEBIESKI` — kolor wiodący |
| `#1fc8ba` turkus | **tylko na granacie** | na białym 2,04:1, poniżej progu 3:1 |
| `#0f9b8e` turkus ciemny | znaczniki na białym | ten sam odcień, kontrast 3,4:1 |

Generator PPTX **wylicza kolory z `generuj.py`**, zamiast trzymać własną kopię. Wcześniej
trzymał i przy zmianie marki obie wersje rozjechały się bez ostrzeżenia: HTML był
granatowy, PowerPoint dalej niebieski.

## Logo w dwóch odmianach

| Plik | Gdzie | Uwaga |
|---|---|---|
| `polmedi-group.png` | prawy górny róg slajdów białych | wersja pełnokolorowa |
| `polmedi-group-logo-white.svg` | **okładka** (tło granatowe) | wersja w kontrze, źródło |
| `polmedi-group-white.png` | okładka w PPTX | rasteryzacja powyższego, robi ją `makiety_png.py` |

PNG w kontrze jest potrzebny, bo `python-pptx` nie przyjmuje SVG. Rasteryzujemy Edge'em
z `--default-background-color=00000000`: znak jest biały, więc na domyślnym białym tle
wyszłaby biel na bieli. Gdyby tego pliku zabrakło, okładka wraca do loga pełnokolorowego
na białym podkładzie — brzydko, ale widocznie.

## Co sprawdzić po zmianie treści

Slajd ma sztywną wysokość, więc treść, która się nie mieści, zostaje **ucięta bez
ostrzeżenia** — layout weryfikujemy na obrazku, nie w kodzie.

1. PDF ma mieć 10 stron o proporcji 1,778 i żadnej uciętej treści.
2. PPTX konwertujemy osobno (`soffice --headless --convert-to pdf` na Sparku) i oglądamy
   strony: **PowerPoint łamie wiersze inaczej niż przeglądarka.** Przy tym wydaniu wyszły
   tą drogą dwa błędy — pusty slajd dziesiąty (mapa `GRAFIKI` w `generuj_pptx.py`
   rozpoznaje slajdy PO TYTULE, więc zmiana tytułu odcina rysowanie) i wizytówki
   nachodzące na pasek puenty.

## Liczby użyte w prezentacji

Czasy (odpowiedź ok. 15 s, przygotowanie dokumentu ok. 60 s) pochodzą z pomiarów na
działającym wdrożeniu. Pojemność „setki tysięcy plików" to rachunek z 4 TB i typowej
wielkości pliku biurowego, nie wynik testu przy takiej skali. **Warunki handlowe są
przeniesione z wydania dla ZCO i wymagają potwierdzenia** przed wysłaniem komukolwiek.
