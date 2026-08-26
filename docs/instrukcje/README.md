# Instrukcje obsługi — ZCO DM i HiRS

Dwadzieścia cztery dokumenty: dwa wdrożenia × sześć języków × dwa wydania, każdy
w HTML i PDF.

| Wydanie | Zakres |
|---|---|
| `instrukcja-administratora.*` | 17 rozdziałów: pełny zakres z uprawnieniami, częścią administracyjną i rozpoznawaniem dokumentów |
| `instrukcja-uzytkownika.*` | 12 rozdziałów: to, co potrzebne na co dzień |

Języki: `pl`, `en`, `cs`, `de`, `es`, `uk` — te same, które ma interfejs.

## Gdzie leżą gotowe pliki

Generator pisze **wprost do katalogu aplikacji**, bo to jedyne miejsce, z którego
instrukcja jest czytana:

```
frontend/public/pomoc/<zco|hirs>/
    zrzuty/*.png                          <- raz na wdrożenie, wspólne dla języków
    <pl|en|cs|de|es|uk>/
        instrukcja-administratora.html    <- obrazki przez ../zrzuty/, ~45 KB
        instrukcja-administratora.pdf     <- samodzielny, do wysłania i do druku
        instrukcja-uzytkownika.html
        instrukcja-uzytkownika.pdf
```

**Dlaczego zrzuty leżą obok, a nie w HTML-u.** Do 1.6.0 były wbudowane jako `data:` URI
i plik ważył 4,5 MB. Przy sześciu językach dałoby to 28 MB tych samych obrazków na
wdrożenie. PDF zostaje samodzielny — jego się wysyła mailem, więc nie może zależeć od
katalogu obok.

Ekran **Pomoc** dobiera plik po języku interfejsu (`useLocale()`), wydanie po roli konta,
a wdrożenie po zmiennej `HELP_VARIANT`.

## Dlaczego jeden generator, a nie cztery dokumenty

Treść rozdziałów jest **wspólna dla obu wdrożeń**, bo obie instancje to ten sam obraz
aplikacji. Różnią się wyłącznie słownikiem `WDROZENIA` na górze `generuj.py` (nazwa,
odbiorca, nazwy plików) i katalogiem ze zrzutami. Gdyby wydania pisać osobno, pierwsza
poprawka trafiłaby tylko do jednego z nich.

Podobnie rozdziały wspólne dla obu ról (`r_*`) są zdefiniowane raz, a `dokument_admina()`
i `dokument_uzytkownika()` składają z nich właściwe wydania.

## Pełne odświeżenie po zmianach w aplikacji

Kolejność ma znaczenie — zrzut ekranu **Instrukcja** pokazuje instrukcję, więc powstaje
dopiero po wdrożeniu poprzedniego kroku.

```bash
# 1. Zrzuty z produkcji: wszystko poza ekranem Instrukcja
python zrzuty_config.py            # cztery przebiegi: zco/hirs × admin/user

# 2. Zmniejszenie zrzutów (13 MB -> 3,4 MB na wdrożenie, bez straty czytelności)
python optymalizuj_zrzuty.py

# 3. Złożenie dokumentów — od razu do katalogu aplikacji, bez kopiowania
python generuj.py                  # 24 dokumenty; `generuj.py zco de` zawęża przebieg
#   commit + push -> CI wdraża ZCO; HiRS ręcznie (zob. główne README)

# 4. Zrzut ekranu Instrukcja — teraz pokazuje już nowe wydanie
ETAP=2 python zrzuty_config.py
python optymalizuj_zrzuty.py && python generuj.py
```

**Kolejność jest wiążąca, a jej naruszenie nie daje żadnego objawu.** Oba kroki
poniżej pominięto raz i za każdym razem dokumenty złożyły się poprawnie:

* **bez `optymalizuj_zrzuty.py`** zrzuty zostają w gęstości 2× (3200 px, pół
  megabajta) — instrukcje wyglądają tak samo, tylko komplet waży 281 MB zamiast
  122 MB. Generator odmawia teraz składania z surowych zrzutów, ale sprawdza
  pierwszy plik w katalogu, nie każdy.
* **wpis o nowym wydaniu musi być w `changelog.json` PRZED złożeniem** — numer
  wersji i datę generator czyta raz, przy starcie. Dopisanie wydania w trakcie
  daje instrukcję z numerem o jeden w tył.

Numeru wersji ani daty NIE wpisuje się już w `generuj.py`: idą z pierwszego wpisu
w `backend/app/changelog.json` (`WERSJA`, `DATA_ISO`, `data_wydania()`).

## Tłumaczenia

Rozdziały są napisane **po polsku i pozostają jedynym źródłem treści**. Tłumaczenia leżą
w `tlumaczenia/<język>.json` jako słownik „polskie zdanie → zdanie obce".

Kluczem jest **całe polskie zdanie**, nie identyfikator. Jest to wybór świadomy: poprawka
polskiego tekstu odcina nieaktualne tłumaczenie i w obcym wydaniu pojawia się zdanie po
polsku. Lepiej to, niż zostawić zdanie mówiące coś innego niż oryginał — a przy kluczach
symbolicznych dokładnie tak by się stało, po cichu.

Czego nie widać w kluczach: nazwy wdrożenia. Dokument składa się ze **znacznikami**
(`⟦NAZWA⟧`, `⟦PELNA⟧`, `⟦WLASCICIEL⟧`), które podmieniamy dopiero w gotowym HTML-u —
inaczej ten sam akapit miałby osobne tłumaczenie dla ZCO i dla HiRS. Wartości zależne
od języka (`szpitala` → `dem Krankenhaus`) siedzą w `WDROZENIA_JEZYKOWO`.

Po każdym przebiegu generator wypisuje, czego nie przetłumaczono. **Cisza byłaby tu
najgorsza** — brak tłumaczenia widać inaczej dopiero przy czytaniu sześćdziesięciu stron
PDF-a.

### Powtórzenie pojedynczego zrzutu

```bash
TYLKO=chat,wyszukiwarka python zrzuty_config.py zco admin de   # wybrane ekrany
ETAP=2 python zrzuty_config.py hirs              # tylko ekran Instrukcja
```

## Zrzuty ekranu

Robi je `shot.py` — Edge w trybie headless sterowany protokołem DevTools, z tokenem sesji
wstrzykniętym do `localStorage`. Konfigurację buduje `zrzuty_config.py`: wie, którego konta
użyć na którym wdrożeniu, i **generuje token po stronie serwera** (`docker exec`), więc
nigdzie nie pojawia się hasło.

Zrzuty idą **przeciwko produkcji** (ZCO `:3000`, HiRS `:3001`) i lądują w `zrzuty/<wdrożenie>/`,
którego nie trzymamy w repozytorium — są już wbudowane w HTML i PDF, a przy zmianie wyglądu
i tak trzeba je zrobić od nowa.

Konta użyte na zrzutach są istniejące; **żadne nie jest zakładane ani kasowane na potrzeby
instrukcji**. Wydanie użytkownika wymaga konta bez uprawnień administratora, które ma dostęp
do jakichkolwiek folderów — na HiRS jest to konto demo „Anna Kowalska" (rola Lekarz).

Możliwości pojedynczego zrzutu:

- `js`, `js2`, `js3` — kolejne kroki po załadowaniu strony (wejście do folderu, zaznaczenie,
  otwarcie okna), każdy z własną pauzą `wait_js*`,
- `clip` — selektor CSS kadrujący zrzut, `clip_js` — wyrażenie zwracające element, gdy
  stabilnego selektora nie ma,
- `wyloguj` — czyści sesję przed nawigacją (ekran logowania), po zrzucie ją przywraca.

Zrzuty okien dialogowych kadrujemy do samego okna (`.fixed.inset-0 > div`), bo pełny ekran
daje w druku nieczytelny obrazek.

### Pułapki, które już kosztowały czas

- **Folder roboczy musi zawierać dokumenty bezpośrednio.** Folder z samymi podfolderami
  (np. „Zarządzenia dyrektora ZCO") nie ma czego kliknąć — zrzuty szczegółów, przenoszenia
  i nadawania nazw wychodzą wtedy jako pełny ekran eksploratora.
- **Czat trzeba doczekać do końca.** Przy zbyt krótkiej pauzie zrzut łapie odpowiedź
  w trakcie pisania, bez listy źródeł — czyli bez tego, co ta ilustracja ma pokazać.
  Stąd `wait_js: 95` i przewinięcie okna rozmowy na dół.
- **Pytanie dobieramy tak, żeby odpowiedź była krótka.** Wyliczanka na dwadzieścia punktów
  wypełnia cały ekran i wypycha źródła poza kadr.

## PDF

Drukuje Edge w trybie headless. Dwie pułapki, obie obsłużone w `do_pdf()`:

- poprawna flaga to `--print-to-pdf-no-header`; wariant `--no-pdf-header-footer` Edge
  po cichu ignoruje i pliku nie tworzy,
- proces Edge kończy się kodem 0 **zanim** dopisze PDF — dlatego czekamy, aż plik powstanie
  i przestanie rosnąć.

## Instrukcja wbudowana w aplikację

Pozycja **Instrukcja** w menu pod inicjałami otwiera stronę `/dashboard/pomoc`, która osadza
plik HTML i daje odnośnik do PDF. Wydanie dobiera się po roli konta, a **wdrożenie po zmiennej
środowiskowej `HELP_VARIANT`** (`zco` albo `hirs`; domyślnie `hirs`). Obraz aplikacji jest
wspólny dla obu instancji, więc niesie oba komplety:

```
frontend/public/pomoc/zco/instrukcja-{administratora,uzytkownika}.{html,pdf}
frontend/public/pomoc/hirs/instrukcja-{administratora,uzytkownika}.{html,pdf}
```

Wyboru **nie opieramy na nazwie instancji z bazy** — od wersji 1.5 administrator może ją
zmienić w Ustawieniach, a instrukcja ma zostać ta właściwa.
