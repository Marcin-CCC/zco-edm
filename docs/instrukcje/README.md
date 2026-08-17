# Instrukcje obsługi — ZCO DM i HiRS

Cztery dokumenty: dwa wdrożenia × dwa wydania, każde w HTML i PDF.

| Plik | Zakres |
|---|---|
| `ZCO-DM-instrukcja-administratora.*` | 17 rozdziałów: pełny zakres z uprawnieniami, częścią administracyjną i rozpoznawaniem dokumentów |
| `ZCO-DM-instrukcja-uzytkownika.*` | 12 rozdziałów: to, co potrzebne na co dzień |
| `HiRS-instrukcja-administratora.*` | jak wyżej, dla demo uniwersalnego |
| `HiRS-instrukcja-uzytkownika.*` | jak wyżej, dla demo uniwersalnego |

Pliki HTML są samodzielne — zrzuty ekranu siedzą w nich jako `data:` URI, więc wystarczy
przesłać jeden plik, bez katalogu z obrazkami.

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

# 2. Zmniejszenie zrzutów (13 MB -> 4,6 MB na wdrożenie, bez straty czytelności)
python optymalizuj_zrzuty.py

# 3. Złożenie dokumentów
python generuj.py                  # oba wdrożenia; `generuj.py zco` tylko jedno

# 4. Do aplikacji i wdrożenie
cp ZCO-DM-instrukcja-administratora.html ../../frontend/public/pomoc/zco/instrukcja-administratora.html
#   … pozostałe trzy pary analogicznie (zco/, hirs/)
#   commit + push -> CI wdraża ZCO; HiRS ręcznie (zob. główne README)

# 5. Zrzut ekranu Instrukcja — teraz pokazuje już nowe wydanie
ETAP=2 python zrzuty_config.py
python optymalizuj_zrzuty.py && python generuj.py
#   ponownie skopiować i wdrożyć
```

Po każdej zmianie zaktualizuj `WERSJA` i `DATA` na górze `generuj.py`.

### Powtórzenie pojedynczego zrzutu

```bash
TYLKO=chat python zrzuty_config.py zco admin     # tylko pliki z „chat" w nazwie
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
