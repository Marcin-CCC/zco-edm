# Plan wprowadzenia wielojęzyczności

Decyzja użytkownika z **25 sierpnia 2026**: robimy pełną wielojęzyczność, zaczynając
od uniezależnienia cytowań od języka. Punktem wyjścia jest wersja **1.5.20**.

Dokumenty pokrewne: [`analiza-wielojezycznosc.md`](analiza-wielojezycznosc.md) —
pomiary i uzasadnienia, na których ten plan stoi.

---

## 0. Punkt powrotu (zrobione 25.08.2026)

Warunek wstępny, bo dalsze kroki ruszają schemat bazy.

| Element | Stan |
|---|---|
| Obrazy `:1.5.20` (backend, frontend) | na Sparku, wypchnięte do ghcr przez CI |
| Tag `v1.5.20` | w repozytorium |
| `edmdatabase-przed-wielojezycznoscia-20260825.sql` | 1,5 MB, 16 tabel |
| `hirsdatabase-przed-wielojezycznoscia-20260825.sql` | 420 kB, 16 tabel |
| `.env.przed-1.5.20` w `~/hirs-app` | jest |

**Zasada obowiązująca w każdym kroku:** do bazy wolno tylko DOKŁADAĆ tabele i kolumny.
Żaden krok nie zmienia znaczenia danych, które już tam są. Dzięki temu cofnięcie
obrazu do 1.5.20 przywraca działającą aplikację bez odtwarzania bazy — interfejs
wraca po polsku, nic nie ginie. Zrzuty są zabezpieczeniem na wypadek pomyłki, a nie
elementem zwykłej drogi powrotu.

---

## 1. Cytowania i odmowy niezależne od języka — ZROBIONE (1.5.21, 25.08.2026)

**Dlaczego pierwsze.** Dziś oba mechanizmy są zaczepione o dosłowne polskie napisy.
Po angielsku model przestaje wystawiać `[Źródło N]`, więc wszystkie źródła dostają
`cited: false` i chowają się pod zwijką. Gorsze jest to, co dzieje się z odmową:
`FORMULKA` w [`app/chat/formulka.py`](../backend/app/chat/formulka.py) to literał,
od którego zależą **cztery** rzeczy — zdejmowanie doklejonego ogona, pominięcie tury
w historii (`_is_refusal`), ponowienie pytania „na czysto" we froncie (`czystaOdmowa`)
i wyzerowanie źródeł w węźle Sources Gate w n8n. Odmowa po angielsku nie zostanie
rozpoznana: trafi do historii i zachowa źródła, z których model nie skorzystał.

**Do zrobienia**

1. Znacznik cytowania: parsery (backend i front) przyjmują postać neutralną `[[N]]`
   **obok** dotychczasowej `[Źródło N]`. Dwie formy naraz, żeby zmiana promptu i
   wdrożenie kodu nie musiały nastąpić w tej samej minucie.
2. Odmowa: model wystawia stały znacznik, którego backend nie pokazuje użytkownikowi,
   tylko podmienia na przetłumaczone zdanie. Rozpoznawanie odmowy przestaje zależeć
   od języka, a samo zdanie może być w języku interfejsu.
3. Prompt w n8n — **zmiana po stronie użytkownika**, razem z „Publish". Dokładna
   instrukcja: [`n8n-zmiany-wielojezycznosc.md`](n8n-zmiany-wielojezycznosc.md).
   Kolejność: najpierw obie aplikacje na 1.5.21, potem „Publish" — jeden workflow
   obsługuje i ZCO DM, i HiRS.

**Sprawdzenie — wynik na ruchu produkcyjnym (25.08.2026, ZCO DM, 5 odpowiedzi):**
odpowiedzi po angielsku mają cytowania (4 z 6 i 3 z 3 źródeł podświetlone; wcześniej
zawsze 0), liczba podświetleń zgadza się z unikalnymi numerami w treści, odmowy
zapisały się jako `[[BRAK]]` z pustą listą źródeł, a `[Źródło N]` / `Source N`
nie wystąpiły ani razu.

**Ryzyko:** to jedyny krok dotykający n8n. Wersja przejściowa rozumie obie postacie,
więc kolejność wdrożeń nie ma znaczenia.

---

## 2. Infrastruktura i18n i przełącznik języka — ZROBIONE (1.5.22, 25.08.2026)

- `next-intl` 4.13: `src/i18n/request.ts` czyta język na serwerze, katalogi w
  `frontend/messages/*.json`, polski bazowy. Katalog innego języka jest DOKŁADANY
  na polski, nie zastępuje go — stąd zapas polskim zdaniem zamiast kluczem.
- Skąd bierze się język, w tej kolejności: ciasteczko `locale` → `DEFAULT_LOCALE`
  wdrożenia → polski. Wybór zapisuje się też przy koncie (nowa kolumna
  `users.locale`, NULL = brak wyboru) i wraca przy logowaniu na innym komputerze.
- Dwie zmienne środowiskowe: `UI_LANGUAGES` (lista włączonych; przy jednej pozycji
  przełącznik znika sam) i `DEFAULT_LOCALE`. Obie w obu plikach compose.
- Przełącznik **na lewo od awatara**, kody ISO 639-1; wybrany znaczony ptaszkiem,
  nie niebieskim tłem — w layoucie 1.5 niebieski jest kolorem akcji.
- Języka przeglądarki NIE pytamy.

**Sprawdzenie (zmierzone na zbudowanym obrazie, nie na kodzie):** ciasteczko `pl`,
`en`, `en-US` daje `<html lang>` zgodny z wyborem, `de` i brak ciasteczka wracają do
domyślnego; `DEFAULT_LOCALE=en` przestawia stronę bez ciasteczka; usunięcie klucza
`shell.logout` z `en.json` pokazuje „Wyloguj", a nie `shell.logout`; przy
`UI_LANGUAGES=pl` stare ciasteczko `en` nie ma prawa przejść.

**Zostaje do kroku 3:** przetłumaczone jest wyłącznie menu przy awatarze (5 napisów).
Ekran logowania nie ma przełącznika — górnej belki tam nie ma; pierwsze wejście jest
w języku wdrożenia, przełączenie po zalogowaniu zostaje na stałe.

---

## 3. Wyciągnięcie napisów — ekran po ekranie (W TOKU)

**Języki (1.5.24):** `pl` (bazowy), `en`, `cs`, `de`, `es`, `uk`. Kompletności
katalogu w obrazie wymagamy WYŁĄCZNIE od angielskiego — nim system się pokazuje.
Pozostałe dochodzą stopniowo: napis bez tłumaczenia wypada po polsku, a uzupełnia
się go w zakładce „Języki". Inaczej każdy nowy przycisk trzeba by przetłumaczyć na
pięć języków, zanim w ogóle dałoby się go wdrożyć.

**Stan 25.08.2026 (1.5.23):** zrobione — ekran logowania, menu boczne,
górna belka, zakładki administratora. Pomiar całości: 348 napisów w 30 plikach
(więcej niż pierwotne 211 — tamten spis pomijał napisy bez znaków diakrytycznych).
Największe pozostałe: Pliki (61), Czat (40), Kolejka plików (39), Lista odpowiedzi (27),
Ustawienia (26), Schematy dokumentów (23), Dashboard (23).

211 unikalnych napisów w 44 plikach. Idziemy partiami, każda osobno sprawdzana:

1. powłoka (sidebar, belka, stopka, okna wspólne),
2. Dashboard,
3. Pliki,
4. Chat z AI,
5. Wyszukiwanie,
6. administracja: Użytkownicy, Lista dostępów, Schematy dokumentów, Kolejka plików,
   Lista odpowiedzi, Ustawienia, Profil, Pomoc, Kontakt.

**Sprawdzenie po każdej partii:** ekran po polsku wygląda identycznie jak przed
zmianą (zrzut przed/po), a po przełączeniu na EN nie ma surowych kluczy.

---

## 4. Liczebniki i formatowanie

Cztery kopie ręcznie pisanej odmiany (`odmiana`, `odmianaPlikow`, `odmianaDokumentow`,
`pluralDocs`) znikają na rzecz formatu ICU — polski ma trzy formy, angielski dwie,
a kolejny język nie dokłada kodu. Dwadzieścia miejsc z zaszytym `pl-PL` idzie
za wyborem języka.

**Uwaga:** kolacja `polish_natural` sortująca pliki zostaje niezależna od interfejsu.
Sortowanie ma iść za językiem DOKUMENTÓW, nie za językiem menu.

---

## 5. Komunikaty backendu

121 komunikatów `detail=`. Dzielimy je:

- **dla użytkownika** — zamieniamy na kody błędów, tłumaczone we froncie,
- **techniczne** (dla administratora i do logu) — zostają po polsku.

---

## 6. Zakładka „Języki" w administracji — ZROBIONE (1.5.23, 25.08.2026)

Wymaganie użytkownika: tłumaczenia muszą dać się poprawiać bez wdrożenia.

**Jak to działa**

1. Administrator dodaje język (kod ISO).
2. Aplikacja tłumaczy **maszynowo** cały katalog — modelem działającym na Sparku,
   więc żaden napis nie opuszcza budynku, tak samo jak dokumenty.
3. Człowiek przegląda listę fraz i poprawia to, co wymaga poprawy.

**Gdzie mieszkają tłumaczenia.** Warstwowo: pliki w repozytorium niosą komplet
(świeża instalacja działa bez ani jednego wpisu w bazie), a tabela `translations`
trzyma WYŁĄCZNIE poprawki administratora i nakłada się na wierzch. Dzięki temu
cofnięcie obrazu nie gubi poprawek, a nowa instalacja nie wymaga bazy tłumaczeń.

**Ekran:** lista fraz z filtrem „nieprzetłumaczone / poprawione ręcznie / wszystkie",
pole źródłowe po polsku obok pola docelowego, oznaczenie fraz tkniętych przez człowieka
(żeby ponowne tłumaczenie maszynowe ich nie nadpisało).

**Jak wyszło.** Ekran `/dashboard/languages`, cztery filtry (wszystkie / brakujące /
maszynowe / poprawione), wyszukiwarka po kluczu i po napisie, zapis przy opuszczeniu
pola. Przycisk „Przetłumacz brakujące" rusza WYŁĄCZNIE napisy, których nie ma —
tekstu sprawdzonego przez człowieka nie nadpisuje.

Dodawanie języka kodem ISO z ekranu ZOSTAJE do zrobienia: lista języków jest na razie
w `UI_LANGUAGES` i w `LOCALES`, bo nowy język wymaga też katalogu `messages/<kod>.json`
w obrazie. Bez niego nie byłoby czego tłumaczyć maszynowo.

**Katalogów nie zna backend** — leżą w obrazie frontendu. Zestawienie „co jest
przetłumaczone" składa więc ekran administratora, a backend trzyma same poprawki.
Kopiowanie katalogów do obrazu backendu dałoby dwie prawdy rozjeżdżające się przy
pierwszym wydaniu.

**Tłumaczenie maszynowe** idzie partiami po 20 napisów przez model na Sparku
(`VLLM_URL`), a wynik wiąże się z wejściem po NUMERZE linii, nie po kolejności.
Zgubiona linia zostawia dziurę do uzupełnienia ręcznie, zamiast przesuwać całą resztę
o jedno miejsce — bez tego przycisk dostałby tłumaczenie nagłówka kolumny i nikt by
tego nie zauważył, bo oba napisy są krótkie.

---

## 7. Język odpowiedzi

Do promptu trafia język interfejsu wraz z zastrzeżeniem, że dokumenty są w innym
języku — **warunkowo**, tylko gdy języki się różnią. Dla polskiego użytkownika
byłoby to szumem, a zbiór przestaje być jednojęzyczny (materiały od dostawców).

Krok wykonalny dopiero **po kroku 1**. Odwrotna kolejność daje demo, w którym znikają
źródła, a odmowy udają odpowiedzi.

---

## Czego ten plan NIE obejmuje

- **Instrukcji obsługi** — cztery dokumenty po polsku, do których prowadzi przycisk
  Pomoc. Ich wersja obcojęzyczna to praca tłumaczeniowa, nie programistyczna.
- **Doboru fragmentów świadomego języka** i **korpusu obcojęzycznego na demo** —
  poziomy 2 i 3 z analizy. Dopiero one dają pokaz, w którym również DOKUMENTY są
  w języku oglądającego.

## Szacunek

| Krok | Dni robocze |
|---|---|
| 1. Cytowania i odmowy | 0,5–1 |
| 2. Infrastruktura i przełącznik | 1 |
| 3. Wyciągnięcie 211 napisów | 2 |
| 4. Liczebniki i formatowanie | 0,5 |
| 5. Komunikaty backendu | 1,5 |
| 6. Zakładka Języki (ekran, tłumaczenie maszynowe, warstwa poprawek) | 2 |
| 7. Język odpowiedzi | 0,5 |
| Tłumaczenie 617 słów i przegląd 44 ekranów | 1,5 |
| **Razem** | **9,5–10** |
