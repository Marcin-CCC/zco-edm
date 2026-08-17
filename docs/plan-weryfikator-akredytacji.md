# Weryfikator zgodności z akredytacją — plan budowy

Dokument planistyczny z **17 sierpnia 2026**. Kontynuacja
[`analiza-agenty.md`](analiza-agenty.md); rejestr standardów jest gotowy
(`tools/accreditation/`, 210 standardów, kontrola kompletności wbudowana).

Przypadek użycia: **użytkownik wskazuje dokument z procedurą, który już jest w Plikach,
i pyta, czy procedura spełnia standardy akredytacyjne.**

---

## 0. Trzy fakty z pomiaru, które ustawiają architekturę

| Fakt | Konsekwencja |
|---|---|
| Procedury mają od ~800 do ~11 500 tokenów (`I 206-012` → `P-206`) | **cała procedura mieści się w jednym wywołaniu**; nie tniemy jej i nie wyszukujemy w niej fragmentów — model widzi wszystko, więc nie ma problemu „brakujący wymóg nie ma do czego być podobny" |
| `doc_extract.py` już woła vLLM z wymuszonym schematem JSON (`response_format: json_schema`, `temperature 0`) | ocena standardu to **ten sam mechanizm**, inny schemat i inny prompt; nie budujemy nowej integracji z modelem |
| W backendzie nie ma infrastruktury zadań długotrwałych — jest tylko watchdog kolejki parsowania | ocena 30–60 standardów × kilkanaście sekund to **minuty**; potrzebna jest tabela zadań, postęp i praca w tle |

Wniosek dla całości: **model dostaje jeden standard i całą procedurę** i odpowiada
w zamkniętym schemacie. Nigdy nie widzi więcej niż jednego standardu naraz. Nigdy nie
liczy punktów.

---

## 1. Plan w punktach

### Etap A — dane (2–3 dni, poza aplikacją)

**A1. Wymagania jako lista, nie proza.** Pole `wymagania` w rejestrze to zdania
(„Szpital powinien: zapewnić…; stosować…"). Agent potrzebuje **listy pojedynczych,
sprawdzalnych wymogów**. Jeden standard na wywołanie modelu, wymuszony schemat:

```json
{ "wymogi": [ { "id": "CO 1.a", "tresc": "…", "typ": "dokument|praktyka|zasob" } ] }
```

Typ wymogu jest istotny: część wymagań dotyczy **treści dokumentu** (da się ocenić
z procedury), część **praktyki** (wywiad, obserwacja — z dokumentu nie da się),
część **zasobów** (sprzęt, personel). Agent oceniający z samego dokumentu ma prawo
oceniać wyłącznie pierwszy typ; pozostałe oznacza jako „do sprawdzenia poza dokumentem".
Bez tego rozróżnienia dostaniemy pewne siebie oceny rzeczy, których w papierze nie ma.

**A2. Zestaw odniesienia.** Rozpisuję ręcznie 12–15 standardów (różne działy, z rubryką
5/3/1 i 5/1). Puszczam model na tych samych. Porównuję. **Dopiero potem** model robi
pozostałe ~195. Bez tego kroku nie wiemy, czy rozbicie na wymogi jest wiarygodne.

**A3. Słowniczek.** Wyciągnięcie „Terminów i określeń" (31 kB) do tabeli
`{pojecie, definicja}`. Trafia do promptu oceniającego jako kontekst, gdy standard
używa pojęcia zdefiniowanego (np. „kamień milowy", „zdarzenie niepożądane").

**A4. Uzupełnienie dwóch rekordów bez wagi** — ręcznie, z PDF-a.

**A5. Rejestr do bazy.** Tabele `accreditation_standards` i `accreditation_requirements`,
ładowane z JSON-a przy starcie (idempotentnie, jak `seed_roles`). Wersjonowane
(`edition = 2025`), bo standardy są nowelizowane.

### Etap B — podbudowa pod zadania długotrwałe (3–4 dni)

To jest **wspólna infrastruktura dla wszystkich przyszłych agentów** — buduje się raz.

**B1. Tabela `agent_jobs`**: id, typ (`accreditation_review`), status
(`queued/running/done/failed/cancelled`), postęp (`done/total`), parametry, wynik
(JSON), kto uruchomił, kiedy. Plus `agent_job_items` na wyniki cząstkowe (jeden
wiersz = jeden oceniony standard), żeby przerwane zadanie dało się wznowić i żeby
postęp był prawdziwy, a nie szacowany.

**B2. Wykonawca w tle.** Pętla w procesie backendu (jak dzisiejszy watchdog), która
bierze zadanie ze statusem `queued`, przetwarza pozycję po pozycji i zapisuje każdą
od razu. Jedno zadanie naraz.

**B3. Arbitraż z czatem.** Ocena to seria wywołań modelu; między nimi wykonawca
sprawdza `activity.chat_active()` i **ustępuje czatowi** — dokładnie tak jak dyspozytor
parsowania. Użytkownik przy czacie nie może czekać, bo ktoś puścił audyt.

**B4. API**: `POST /api/agents/accreditation` (start), `GET /api/agents/jobs/{id}`
(stan + postęp + wynik cząstkowy), `POST …/cancel`, `GET /api/agents/jobs` (historia).
Uprawnienia: uruchomić może każdy, kto ma odczyt do dokumentu; wynik widzi ten,
kto uruchomił, i administrator.

### Etap C — sam agent (1 tydzień)

**C1. Wybór standardów do oceny.** Nie oceniamy 210 standardów dla każdej procedury —
większość jest nie na temat. Dwa źródła wyboru:
- **wybór użytkownika** (dział albo konkretne standardy — zob. interfejs),
- **propozycja modelu**: jedno wywołanie z tytułami wszystkich 210 standardów (to ~6 k
  tokenów) i streszczeniem procedury → lista kodów „prawdopodobnie dotyczy". Użytkownik
  zatwierdza listę **przed** startem oceny.

**C2. Pętla oceny.** Dla każdego wybranego standardu jedno wywołanie:

```
WEJŚCIE : standard (tytuł, wymogi z A1, rubryka 5/3/1, definicje ze słowniczka)
          + pełny tekst procedury
WYJŚCIE : { "wymogi": [ { "id", "stan": "spelniony|niespelniony|nie_do_ustalenia",
                          "cytat": "…dosłowny fragment procedury…" | null,
                          "uzasadnienie": "…" } ],
            "proponowana_ocena": 5|3|1|null,
            "uwagi": "…" }
```

Trzy stany, nie dwa. **Cytat obowiązkowy przy „spełniony"** i weryfikowany w kodzie:
jeśli podanego cytatu nie ma dosłownie w tekście procedury, stan spada do
„nie do ustalenia", a pozycja dostaje flagę do ręcznego sprawdzenia. To jedyna twarda
zapora przed konfabulacją.

**C3. Punktacja w kodzie.** Ocena 5/3/1 wynika z rubryki i udziału spełnionych
wymogów; waga z rejestru; standardy obligatoryjne oznaczone osobno (niespełniony
obligatoryjny = czerwona flaga niezależnie od procentu). Model może **zaproponować**
ocenę, ale liczba w raporcie pochodzi z kodu i jest odtwarzalna.

**C4. Raport.** Zapis w `agent_jobs.result` + eksport do XLSX (mamy `eksport.py`) —
arkusz „Podsumowanie" i arkusz „Szczegóły" (wymóg po wymogu z cytatami).

### Etap D — interfejs (3–4 dni)

Opisany w punkcie 2.

### Etap E — pomiar przed pokazaniem komukolwiek (nieokreślony, zależy od szpitala)

**Warunek startu etapu C: 3–5 procedur ocenionych wcześniej przez dział jakości.**
Bez wzorca nie wiemy, czy agent ocenia dobrze — i nie ma sposobu, żeby się tego
dowiedzieć inaczej. Miary: zgodność stanu wymogu (spełniony/nie) z oceną człowieka,
odsetek cytatów trafnych, odsetek „nie do ustalenia" tam, gdzie człowiek też się wahał.

---

## 2. Propozycja interfejsu

### Zasada

**Wejście z dokumentu, nie z osobnego ekranu.** Użytkownik jest w Plikach, ma przed sobą
procedurę i pyta „czy to spełnia akredytację". Osobny ekran „Weryfikator" z wyborem
dokumentu z listy to o jeden krok za dużo — i myli, gdy dokumentów są setki.

Do tego jeden ekran administracyjny na **historię ocen**, bo raporty muszą gdzieś żyć.

### 2.1. Start — z okna szczegółów dokumentu

W istniejącym oknie szczegółów pliku (to, które ma „Pobierz", „Podgląd", „Usuń")
dochodzi przycisk:

```
[ ⬇ Pobierz plik ]  [ 👁 Podgląd ]  [ ✓ Sprawdź zgodność z akredytacją ]  [ 🗑 Usuń ]
```

Widoczny tylko dla dokumentów ze statusem *Przetworzono* (bez tekstu nie ma czego
oceniać) i tylko gdy rejestr standardów jest załadowany.

### 2.2. Okno konfiguracji oceny

Jedno okno modalne, trzy części, jeden przycisk startu.

```
┌─ Sprawdzenie zgodności z akredytacją ────────────────────────────────┐
│ Dokument:  I 206-002 Opieka pielęgniarska.odt                        │
│ Standardy: Standardy Akredytacyjne — szpitale, wydanie 2025          │
│                                                                      │
│ Które standardy sprawdzić?                                           │
│  (•) Zaproponuj automatycznie      ← domyślne                        │
│  ( ) Wybrany dział:  [ OP — Opieka nad pacjentem      ▾ ]            │
│  ( ) Wskażę sam                                                      │
│                                                                      │
│  Zaproponowano 14 standardów (kliknij, aby odznaczyć):               │
│  [✓] OP 1  Pacjenci mają zapewnioną opiekę pielęgniarską…            │
│  [✓] OP 3  Ocena stanu pacjenta jest dokumentowana…                  │
│  [✓] KZ 1.1 Personel uczestniczy w szkoleniach…                      │
│  [ ] JZ 4  Szpital prowadzi politykę…            (odznaczony)        │
│  …                                                                   │
│  + dodaj standard po kodzie: [ PP 3      ] [Dodaj]                   │
│                                                                      │
│ ⓘ Ocena zajmie około 4 minut. W tym czasie możesz korzystać          │
│   z aplikacji — powiadomimy Cię, gdy raport będzie gotowy.           │
│                                                                      │
│                                        [ Anuluj ]  [ Rozpocznij ]    │
└──────────────────────────────────────────────────────────────────────┘
```

Szacunek czasu liczony z liczby standardów × zmierzony czas jednego wywołania —
prawdziwy, nie „chwilę".

### 2.3. W trakcie — pasek postępu, nie blokada

Po starcie okno się zamyka. W prawym górnym rogu (przy avatarze) pojawia się dyskretny
wskaźnik `Ocena w toku · 6/14`, klikalny → prowadzi do raportu z częściowymi wynikami.
Standardy ocenione są widoczne od razu; nieocenione mają szary stan „w kolejce".

Użytkownik może wyjść, wrócić, wylogować się. Zadanie idzie w tle na serwerze.

### 2.4. Raport — osobna strona `/dashboard/akredytacja/{id}`

```
Sprawdzenie zgodności · I 206-002 Opieka pielęgniarska.odt · 17.08.2026 12:40 · Piotr Piątek

┌─────────────────────────────────────────────────────────────────────┐
│  Wynik ważony:  3,9 / 5,0        Standardy: 14 ocenionych           │
│  ● 8 spełnione   ● 3 częściowo   ● 1 niespełniony   ○ 2 nie do      │
│                                                        ustalenia    │
│  ⚠ 1 standard obligatoryjny niespełniony (KZ 1.1)                    │
└─────────────────────────────────────────────────────────────────────┘

[ Pobierz raport XLSX ]   [ Powtórz ocenę ]   [ Oznacz jako przejrzany ]

Standardy (kliknij, aby rozwinąć)
─────────────────────────────────────────────────────────────────────
▸ OP 1   Pacjenci mają zapewnioną opiekę pielęgniarską…    5/5  ●
▾ OP 3   Ocena stanu pacjenta jest dokumentowana…          3/5  ●  waga 0,5
    ✓ Ocena wykonywana przy przyjęciu
      „Pielęgniarka dokonuje oceny stanu pacjenta w chwili przyjęcia
       na oddział…"                                        [otwórz s. 3]
    ✓ Ocena powtarzana w trakcie pobytu
      „…oraz co 24 godziny lub przy zmianie stanu."         [otwórz s. 3]
    ✗ Skala oceny określona w dokumencie
      Nie znaleziono w procedurze wskazania konkretnej skali.
    ? Personel przeszkolony z użycia skali        — do sprawdzenia poza dokumentem
                                                     (wymóg dotyczy praktyki, nie treści)
    Rubryka standardu: 5 — …zgodnie z wymogami · 3 — …w przeważającej części
    · 1 — …nie wdrożył                              Proponowana: 3   [zmień ▾]
▸ KZ 1.1 Personel uczestniczy w szkoleniach…               1/5  ●  OBLIGATORYJNY
…
```

Rzeczy, które nie są ozdobą:

- **Trzy stany plus „poza dokumentem"** — widać wprost, czego z papieru ocenić się nie
  da, zamiast udawać, że da się wszystko.
- **Cytat z odsyłaczem do strony** — kliknięcie otwiera dokument w podglądzie; to jest
  weryfikowalność w praktyce, a nie w deklaracji.
- **`[zmień ▾]` przy proponowanej ocenie** — człowiek nadpisuje, nadpisanie jest
  zapamiętane i widoczne w raporcie jako „ocena ręczna". Agent proponuje, człowiek
  decyduje.
- **Obligatoryjny niespełniony na samej górze**, na czerwono, niezależnie od średniej.
- **„Oznacz jako przejrzany"** — raport bez tego znaku jest wynikiem maszyny;
  ze znakiem jest wynikiem, za którym ktoś stoi.

### 2.5. Historia — `/dashboard/akredytacja` (Administracja)

Lista wszystkich ocen: dokument, data, kto, liczba standardów, wynik, czy przejrzana.
Filtr po dokumencie pozwala zobaczyć, jak zmieniała się zgodność tej samej procedury
między wersjami — to jest realna wartość dla działu jakości.

Pozycja w menu administracyjnym: **Akredytacja**. Rejestr standardów (tabela 210
pozycji, przeszukiwalna, z filtrem po dziale) jest zakładką tego samego ekranu — użyteczna
sama w sobie, zanim ktokolwiek uruchomi ocenę.

---

## 3. Czego świadomie NIE ma w tym planie

- **Oceny „całego szpitala"** — jedna procedura na raz. Ocena zbiorcza to suma ocen
  jednostkowych i wymaga mapowania procedur na standardy, którego dziś nie ma.
- **Automatycznego uruchamiania po wgraniu** — ocena jest świadomym aktem, nie skutkiem
  ubocznym; koszt modelu jest realny.
- **Werdyktu „szpital spełnia / nie spełnia akredytację"** — raport jest materiałem
  dla działu jakości, nie orzeczeniem, i musi to mówić wprost w nagłówku.

---

## 4. Kolejność i koszt

| Etap | Zakres | Czas |
|---|---|---|
| A | dane: wymogi z modelu + zestaw odniesienia, słowniczek, rejestr w bazie | 2–3 dni |
| B | podbudowa zadań w tle (wspólna dla przyszłych agentów) | 3–4 dni |
| C | agent: wybór, pętla, punktacja, raport | ~1 tydzień |
| D | interfejs: przycisk, okno, raport, historia | 3–4 dni |
| E | pomiar na procedurach ocenionych przez dział jakości | zależy od szpitala |

Około **3–4 tygodni** do wersji, którą można pokazać działowi jakości; **etap E
rozstrzyga, czy można ją pokazać komukolwiek innemu.**

Pierwszym krokiem jest A2 — zestaw odniesienia. Bez niego kolejne etapy budują na
danych, których jakości nie znamy.
