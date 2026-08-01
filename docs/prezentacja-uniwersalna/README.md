# EDMund — prezentacja uniwersalna

Wersja handlowa dla dowolnego klienta: bez nazw i zrzutów ekranu konkretnego wdrożenia,
w kolorach polmedi.com. 11 slajdów, ostatni kontaktowy.

- `EDMund-prezentacja.html` — do pokazywania (slajdy 1280 × 720, przewijane),
- `EDMund-prezentacja.pdf` — do wysłania (11 stron 338,7 × 190,5 mm, czyli 16:9),
- `EDMund-prezentacja.pptx` — do samodzielnego poprawiania w PowerPoincie; wszystko jest
  natywnymi kształtami i polami tekstowymi, notatki prelegenta w panelu notatek.

```bash
python generuj.py          # HTML + PDF
python makiety_png.py      # makiety ekranów do PPTX (wymaga Edge)
python generuj_pptx.py     # PPTX
```

Treść slajdów jest w `generuj.py` (stałe `SLAJDY`, `KROKI_SCIEZKI`, `CZASY`, `CENNIK`,
`OSOBY_KONTAKT` …) i stamtąd bierze ją także wersja PowerPointowa — obie nie mogą się
rozjechać. Zmieniając teksty, zmieniamy je w jednym miejscu i generujemy wszystkie trzy pliki.

## Czym różni się od `docs/prezentacja`

`docs/prezentacja` to wersja dla ZCO: nazwa klienta, zrzuty z jego instancji, kolory ZCO DM.
Tutaj:

- nazwa systemu **EDMund** (Enterprise Document Management — „czyli mów mi Mundek”),
- kolory z polmedi.com: `#2448c8` niebieski, `#09afaf` turkus, przejściówka niebiesko-turkusowa,
  tekst `#465050`; turkus na białym daje 2,64:1, więc do napisów używamy ciemniejszego
  `#0a9a9a`, a jasnego wyłącznie na granacie i w gradiencie,
- zamiast zrzutów ekranu — makiety rysowane stylami (`makieta_pliki`, `makieta_czat`),
  z neutralnymi przykładami folderów i rozmowy; do PPTX renderowane do PNG,
- przykłady dziedzinowe zamiast onkologicznych, bez liczby dokumentów z wdrożenia.

## Sprawdzenie po zmianie

Layout weryfikujemy na obrazku, nie w kodzie:

1. `generuj.py` na koniec liczy slajdy z przepełnieniem — ma być 0, a PDF 11 stron
   o proporcji 1,778;
2. PPTX konwertujemy na Sparku (`soffice --headless --convert-to pdf`) i oglądamy strony —
   PowerPoint łamie wiersze inaczej niż przeglądarka, więc teksty w kafelkach trzeba obejrzeć.
