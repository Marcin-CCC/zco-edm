# Prezentacja sprzedażowa ZCO Document Management

Jedenaście slajdów 16:9 w trzech postaciach, z jednego źródła:

- `ZCO-DM-prezentacja.html` — do pokazania z laptopa. Slajd ma stały rozmiar 1280×720 px
  i skaluje się do okna. Klawisze: `→` `←` slajdy, `P` tryb pokazu (jeden slajd na pełnym
  ekranie), `N` notatki prelegenta.
- `ZCO-DM-prezentacja.pdf` — do wysłania. Jedna strona = jeden slajd, 338,667 × 190,5 mm
  (te same 1280×720 px przy 96 dpi), bez marginesów i nagłówków.

- `ZCO-DM-prezentacja.pptx` — do samodzielnego poprawiania w PowerPoincie. Wszystko
  jest natywnymi kształtami i polami tekstowymi (jedyne obrazki to zrzuty ekranu), więc
  każdy element da się kliknąć i zmienić. Notatki prelegenta trafiają do panelu notatek.

```bash
python generuj.py        # HTML + PDF
python generuj_pptx.py   # PPTX (wymaga: pip install python-pptx)
```

Treść infografik siedzi w stałych na górze `generuj.py` (`KROKI_SCIEZKI`, `CZASY`,
`CENNIK`, `OSOBY_KONTAKT`…), z których korzystają OBA generatory — dzięki temu wersja
do pokazania i wersja do edycji nie rozjadą się w treści. Zmiana tekstu w jednym miejscu
przechodzi do HTML, PDF i PPTX.

Podgląd PPTX bez PowerPointa: `soffice --headless --convert-to pdf` na Sparku
(LibreOffice jest tam zainstalowany) — tak sprawdzałem układ slajdów.

Zrzuty ekranu brane są z `../instrukcje/zrzuty/` — tego samego kompletu, co instrukcja
obsługi, więc prezentacja nie rozjeżdża się z aplikacją.

## Kolory i ich rola

Sprawdzone walidatorem palet (tryb jasny, powierzchnia biała):

| Kolor | Rola | Uwaga |
|---|---|---|
| `#1d2a4d` granat | tło paneli, kolor pisma | nie służy jako kolor znacznika |
| `#1fc8ba` turkus marki | **tylko na granacie** | na białym ma 2,04:1 — poniżej progu 3:1 |
| `#0f9b8e` turkus ciemny | znaczniki na białym | ten sam odcień, kontrast 3,4:1 |
| `#2563eb` niebieski | druga seria | para z `#0f9b8e`: ΔE 21,3 przy zaburzeniach widzenia barw |

Każdy znacznik ma podpis wprost przy sobie — kolor nigdy nie niesie znaczenia sam.

## Co warto sprawdzić po zmianie treści

Slajd ma sztywną wysokość, więc treść, która się nie mieści, zostanie w PDF ucięta bez
ostrzeżenia. Kontrola maszynowa (porównuje `scrollHeight` z `clientHeight` każdego slajdu
i weryfikuje format stron PDF) — zob. `sprawdz_prezentacje.py` w katalogu roboczym sesji;
w skrócie: po `generuj.py` otwórz HTML i upewnij się, że żaden slajd nie ma paska
przewijania.

## Liczby użyte w prezentacji

Pochodzą z wdrożenia demonstracyjnego (157 dokumentów): odpowiedź ok. 15 s, przygotowanie
dokumentu ok. 60 s. Pojemność „setki tysięcy plików" to rachunek z 4 TB i typowej wielkości
pliku biurowego — nie wynik testu przy takiej skali. Warunki handlowe (brak opłat za
użytkownika, terminy) są założeniami do potwierdzenia przed wysłaniem klientowi.
