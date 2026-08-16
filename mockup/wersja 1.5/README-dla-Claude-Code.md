# Makieta layoutu — wersja 1.5 (ZCO DM / HiRS)

Statyczne makiety HTML nowego layoutu aplikacji. Jeden plik = jeden ekran, każdy samodzielny
(style w `<style>` w `<head>`, brak zależności zewnętrznych, brak frameworków).
Makiety są **referencją wizualną i interakcyjną**, nie kodem produkcyjnym.

## Ekrany

| Plik | Ekran | Widoczny dla |
|---|---|---|
| `01_dashboard.html` | Dashboard | wszyscy |
| `02_eksplorator_plikow.html` | Pliki | wszyscy |
| `03_chat_ai.html` | Chat z AI | wszyscy |
| `04_wyszukiwanie.html` | Wyszukiwanie (builder zapytań po metadanych) | wszyscy |
| `05_uzytkownicy.html` | Użytkownicy | administrator |
| `06_lista_dostepow.html` | Lista dostępów | administrator |
| `07_schematy_dokumentow.html` | Schematy dokumentów | administrator |
| `08_kolejka_plikow.html` | Kolejka plików | administrator |
| `09_lista_odpowiedzi.html` | Lista odpowiedzi | administrator |
| `10_ustawienia_aplikacji.html` | Ustawienia aplikacji | administrator |
| `11_kontakt.html` | Skontaktuj się (z przycisku w sidebarze) | wszyscy |

Numeracja plików odpowiada kolejności pozycji w menu bocznym.

## Nawigacja

- **Sidebar** — nad kreską: Dashboard, Pliki, Chat z AI, Wyszukiwanie. Pod kreską (tylko admin):
  Użytkownicy, Lista dostępów, Schematy dokumentów, Kolejka plików, Lista odpowiedzi, Ustawienia aplikacji.
- **Zwijanie sidebara** — kliknięcie w logo przełącza `body.collapsed`: szerokość 244 → 72 px, znikają etykiety
  (`.lbl`), panel pomocy zwija się do ikony koła ratunkowego, stopka do samego znaku ©, który jest linkiem do
  strony dostawcy. Tooltipy pozycji z atrybutu `title`.
- **Górne menu administracyjne** (`.admin-tabs`) powtarza pozycje spod kreski z tymi samymi ikonami —
  równoległa droga przechodzenia między ekranami administracyjnymi.
- Przycisk „Skontaktuj się" w sidebarze prowadzi do `11_kontakt.html`.

## System wizualny

- Tokeny w `:root`: `--navy`, `--blue` #2563eb, `--blue2` #1d4ed8, `--bg` #f5f7fb, `--text` #13233f,
  `--muted`, `--line` #e5ebf4, `--green`, `--danger`, `--shadow`. Nie wprowadzać kolorów spoza tej palety.
- Karty: `border-radius:14px`, 1 px obramowania `--line`, delikatny cień `--shadow`.
- Ikony: własne SVG w stylu Lucide — `stroke:currentColor`, `stroke-width` 1.7–1.8, `fill:none`, 16–20 px.
  Zero glifów unicode w roli ikon.
- **Ikony typów plików** (`.fileicon`) są zawsze kwadratowe (32×32): PDF `#d62828`, DOCX i ODT `#2f66dc`,
  XLSX `#20a25a`. Awatary i pola ikon także kwadratowe/okrągłe o stałym rozmiarze (`flex:none`).
- Niebieski = kolor akcji. Stan (aktywna zakładka, bieżąca strona, wybrany widok) nigdy nie jest niebieskim
  wypełnieniem: przełącznik Lista/Kafelki i paginacja używają szarego tła z białym elementem aktywnym.
- Hover: przyciski `primary` przyciemniają się do `--blue2`, aktywne do #1a45c0; wiersze list i karty
  dostają tło `#f6f8fc` i kursor-łapkę. Fokus klawiatury: `outline:2px solid var(--blue); offset 2px`.
- Akcje w wierszach i na kartach folderów pojawiają się dopiero po najechaniu, jako kwadratowe przyciski
  30×30 z tooltipem: ołówek zielony (edycja), kłódka niebieska (uprawnienia), kosz czerwony (usunięcie).

## Interakcje zasymulowane w makiecie

- `02` — nawigacja po drzewie folderów (klik w kartę wchodzi w głąb, breadcrumb wraca), modal szczegółów pliku,
  przełącznik Lista/Kafelki, akcje na hover.
- `03` — lista źródeł odpowiedzi z numerem cytatu, kolorową ikoną typu, rodzajem dokumentu, stroną i nazwą pliku;
  sekcja „Sprawdzono też N dokumentów" rozwijana przyciskiem.
- `04` — budowanie warunków (dodawanie/usuwanie wierszy), przełącznik widoku wyników (lista domyślna).
- `05` — ten sam formularz obsługuje dodawanie i edycję użytkownika.
- `06` — modale „Nowa rola" i „Zmień nazwę roli".
- `07` — kolejność pól nagłówkowych zmienia się **przeciąganiem** za uchwyt (`.grip`); w makiecie jest sam
  uchwyt i kursor `grab`, mechanikę drag & drop trzeba zaimplementować (bez strzałek góra/dół).
- `08` — modal szczegółów pozycji przejmuje status i kategorię z klikniętego wiersza.
- `09` — karty pytań rozwijane do odpowiedzi ze źródłami; kolory źródeł: niebieski = cytowany znacznikiem,
  szary = był w kontekście, żółty = dobrany poza progiem trafności.
- `10` — podgląd identyfikacji aplikacji na żywo: podmiana ikony (PNG/SVG, kwadratowa), nazwa i kolor napisu
  z próbek albo własny HEX, z ostrzeżeniem o kontraście < 4,5:1 na tle menu.

## Czego makieta NIE definiuje

Danych produkcyjnych (wszystkie wiersze i liczby są przykładowe), routingu, uprawnień po stronie serwera,
walidacji formularzy, obsługi błędów i stanów pustych innych niż „Brak plików w tym folderze",
oraz responsywności poniżej ~700 px (makieta była projektowana pod desktop; breakpointy 1350/1100/900 px
są punktem wyjścia, nie kompletnym widokiem mobilnym).
