# Instrukcje obsługi ZCO Document Management

Dwa wydania instrukcji dla klienta (ZCO Szczecin), każde w HTML i PDF:

- `ZCO-DM-instrukcja-administratora.html` / `.pdf` — 17 rozdziałów: pełen zakres łącznie
  z uprawnieniami, częścią administracyjną i opisem rozpoznawania dokumentów,
- `ZCO-DM-instrukcja-uzytkownika.html` / `.pdf` — 12 rozdziałów: to, co potrzebne osobie
  korzystającej z bazy wiedzy na co dzień.

Pliki HTML są samodzielne — zrzuty ekranu siedzą w nich jako `data:` URI, więc wystarczy
przesłać jeden plik, bez katalogu z obrazkami.

## Jak to odtworzyć po zmianach w aplikacji

Oba wydania powstają z jednego źródła: `generuj.py`. Rozdziały wspólne dla obu ról
zdefiniowane są raz (funkcje `r_*`), a `dokument_admina()` i `dokument_uzytkownika()`
składają z nich właściwe wydania — dzięki temu opis tego samego ekranu nie rozjeżdża się
między instrukcjami.

```bash
python generuj.py [katalog_ze_zrzutami]
```

Domyślnie zrzuty brane są z podkatalogu `zrzuty/`, którego **nie trzymamy w repozytorium** (są już wbudowane w HTML i PDF, a przy zmianie wyglądu aplikacji i tak trzeba je zrobić od nowa). Nazewnictwo: `aNN-*.png` dla wydania
administratora, `uNN-*.png` dla wydania użytkownika — nazwy plików są przywoływane wprost
w `generuj.py`.

Przy zmianie wyglądu aplikacji trzeba odświeżyć zrzuty. Robi je skrypt `shot.py`
(Edge headless sterowany protokołem DevTools, z wstrzykniętym tokenem sesji), uruchamiany
osobno dla konta administratora i konta zwykłego użytkownika. Zrzuty okien dialogowych
kadrowane są do samego okna selektorem `.fixed.inset-0 > div`, bo pełny ekran daje
nieczytelny w druku obrazek.

Po każdej zmianie należy zaktualizować stałe na górze `generuj.py`: `WERSJA` i `DATA`.

## Uwagi techniczne

PDF drukuje Edge w trybie headless. Dwie pułapki, obie już obsłużone w kodzie:

- poprawna flaga to `--print-to-pdf-no-header`; wariant `--no-pdf-header-footer` Edge
  po cichu ignoruje i pliku nie tworzy,
- proces Edge kończy się kodem 0 **zanim** dopisze PDF — dlatego `do_pdf()` czeka, aż plik
  powstanie i przestanie rosnąć.

## Instrukcja wbudowana w aplikację

Od wersji 1.0.0 oba wydania są też dostępne w samej aplikacji — pozycja **Pomoc**
w menu pod inicjałami. Strona `/dashboard/pomoc` osadza plik HTML i daje odnośnik do PDF,
a wydanie dobiera się po roli konta. Pliki leżą w `frontend/public/pomoc/`:

```bash
python generuj.py
cp ZCO-DM-instrukcja-administratora.html ../../frontend/public/pomoc/instrukcja-administratora.html
cp ZCO-DM-instrukcja-administratora.pdf  ../../frontend/public/pomoc/instrukcja-administratora.pdf
cp ZCO-DM-instrukcja-uzytkownika.html    ../../frontend/public/pomoc/instrukcja-uzytkownika.html
cp ZCO-DM-instrukcja-uzytkownika.pdf     ../../frontend/public/pomoc/instrukcja-uzytkownika.pdf
```

Kolejność przy odświeżaniu zrzutów jest istotna: zrzut strony Pomoc pokazuje instrukcję,
więc najpierw generujemy wydanie bez niego (brakujący plik zrzutu jest pomijany
z ostrzeżeniem, nie przerywa generowania), kopiujemy do `public/`, przebudowujemy
frontend, robimy zrzut Pomocy i generujemy wydanie ponownie.

Zrzuty robi `shot.py` przeciwko ŚWIEŻEMU buildowi frontendu (`npx next start -p 3010`
z `BACKEND_URL` wskazującym backend deweloperski) — kontener deweloperski serwuje
starą paczkę, więc zrzuty z niego nie pokazałyby nowych zmian. Wydanie użytkownika
wymaga konta bez uprawnień administratora; tworzymy je tymczasowo (rola `office_staff`
ma dostęp do jednego folderu) i kasujemy zaraz po zrzutach.
