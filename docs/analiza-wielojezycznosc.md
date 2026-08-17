# Wielojęzyczność — analiza i plan

Dokument źródłowy do przygotowania wersji językowych aplikacji.
Stan na **17 sierpnia 2026, wersja 1.5.13**. Wszystkie liczby są zmierzone w kodzie
i na działających instancjach, nie oszacowane.

---

## 1. Trzy osie, których nie wolno mieszać

| Oś | Pytanie | Czy da się przełączyć | Koszt |
|---|---|---|---|
| **Interfejs** | w jakim języku są przyciski i komunikaty | tak, per konto | niski |
| **Rozmowa** | w jakim języku pytam i dostaję odpowiedź | tak, per pytanie | średni |
| **Dokumenty** | w jakim języku jest zbiór | **nie — to dane** | wysoki |

Trzecia oś jest kluczowa dla każdej decyzji architektonicznej. Interfejs i rozmowa
to ustawienia; korpus to zawartość bazy i kolekcji wektorów. Nie da się go „przełączyć",
można tylko mieć drugi.

---

## 2. Jak to naprawdę działa — nie ma tłumaczenia

Naturalne przypuszczenie brzmi: pytanie po angielsku jest tłumaczone na polski,
wyszukiwanie idzie po polsku, odpowiedź powstaje po polsku i wraca przetłumaczona.
**Tak to nie działa.** W kodzie nie ma żadnego kroku tłumaczenia — jedyne wystąpienia
słowa „translate" to usuwanie ogonków i transliteracja nazw plików.

Rzeczywisty przebieg:

```
pytanie (dowolny język)
   → bge-m3 zamienia je na wektor ZNACZENIA
   → dopasowanie do polskich fragmentów w tej samej przestrzeni wektorowej
   → polskie fragmenty trafiają do promptu BEZ ZMIAN
   → model czyta po polsku i pisze w języku odpowiedzi
```

Działa to, bo **bge-m3 jest modelem wielojęzycznym** (ponad 100 języków) i umieszcza
zdania o tym samym znaczeniu blisko siebie niezależnie od języka. „Business trip
settlement" i „rozliczenie delegacji" lądują w tym samym miejscu przestrzeni.

**Dowód z pomiaru.** To samo pytanie zadane po polsku (rozmowa 287) i po angielsku
(rozmowa 288) znalazło **te same osiem dokumentów**. Gdyby istniał pivot przez polski,
dobór by się różnił.

Dlaczego to dobra wiadomość: tłumaczenie tam i z powrotem gubiłoby znaczenie dwa razy
i podwajało czas odpowiedzi. Najdroższy element wielojęzycznego RAG-u mamy już rozwiązany
i nie ma w nim czego stroić.

---

## 3. Zdiagnozowana usterka: znikające źródła poza polskim

### Objaw

Pytanie *„show a sample business trip settlement form. Reply in English."* dało dobrą
odpowiedź, ale **bez wskazania źródła**.

### Pomiar

| | pytanie PL (287) | pytanie EN (288) |
|---|---|---|
| znalezione dokumenty | 8 | 8 — te same |
| znacznik cytowania w treści | `[Źródło 1]` | **żaden** |
| oznaczone jako użyte (`cited`) | 3 z 8 | **0 z 8** |
| co widzi użytkownik | lista źródeł | „Sprawdzono też 8 dokumentów…" i nic powyżej |

### Przyczyna

Wyszukiwanie zadziałało bez zarzutu. Zawiodła **konwencja cytowania**: instrukcja
w prompcie jest po polsku i każe wstawiać polskie słowo. Odpowiadając po angielsku,
model porzuca całą konwencję i nie wystawia żadnego znacznika. Wszystkie źródła
dostają wtedy `cited: false` i interfejs chowa je pod zwijką „niewykorzystane".

To samo stało się przy pytaniu po ukraińsku (rozmowa 287, druga tura).

### Dwa twarde powiązania z polskim w kodzie

**Znacznik cytowania** — `frontend/src/app/dashboard/chat/page.tsx`:

```js
const INLINE_MARKER_RE = /\[{1,2}\s*Źród(?:ło|ła)\s*(\d+…)/gi
```

**Wykrywanie odmowy modelu** — ten sam plik:

```js
const ODMOWA_PELNA = 'niestety, nie znaleziono w dokumentach informacji na ten temat.'
```

Oba są dopasowaniem do polskiego tekstu. W innym języku pierwszy nie znajdzie znacznika,
drugi nigdy nie będzie prawdziwy.

### Naprawa

Znacznik niezależny od języka (`[[1]]`) plus instrukcja o cytowaniu wyrażona w języku
odpowiedzi. Analogicznie ustalony znacznik odmowy zamiast porównywania zdania.
**Pół dnia. Do zrobienia niezależnie od decyzji o wielojęzyczności** — dziś ten błąd
jest niewidoczny wyłącznie dlatego, że wszyscy piszą po polsku.

---

## 4. Interfejs — zmierzona skala

| Co | Ile |
|---|---|
| Napisy widoczne w interfejsie (unikalne) | **211** |
| Słów w tych napisach | **617** |
| Plików frontendu | 44 |
| Komunikaty backendu trafiające do użytkownika (`detail=`) | **157** |
| Miejsca z zaszytym `pl-PL` / `localeCompare('pl')` | 18 |
| Kopie ręcznie pisanej polskiej odmiany liczebników | **4** |

617 słów to dwie strony tekstu — dzień pracy tłumacza na język. Kosztem jest
jednorazowe okablowanie: 2–3 dni.

**Rekomendacja: next-intl.** Nie z przywiązania do biblioteki, tylko z dwóch powodów:

- *Liczebniki.* Cztery kopie ręcznie pisanej odmiany (`odmiana`, `odmianaPlikow`,
  `odmianaDokumentow`, `pluralDocs`) znikają. Polski ma trzy formy, arabski sześć —
  format ICU zna reguły dla wszystkich języków, więc kolejny język nie dokłada kodu.
- *Formatowanie.* Osiemnaście miejsc z `pl-PL` musi iść za wyborem języka.

**Skąd język:** domyślny dla wdrożenia (zmienna środowiskowa, jak dzisiejsze
`HELP_VARIANT`) plus nadpisanie per konto w Profilu. Języka przeglądarki nie używać
jako źródła prawdy — na wspólnym komputerze interfejs zmieniałby język między zmianami.

**Komunikaty backendu:** podzielić. Te, które użytkownik ma zrozumieć — zamienić
na kody błędów i tłumaczyć na froncie. Techniczne, trafiające do administratora
i do logu — zostawić po polsku.

### Czego słownik nie przetłumaczy

- **nazwy folderów** — dane klienta,
- **nazwy kategorii dokumentów** (Zarządzenie, Aneks) — rejestr schematów, widoczne
  w wynikach i pod odpowiedziami czatu,
- **nazwy pól opisowych** (`numer_dokumentu`) — jw.,
- **treść dokumentów** — z natury.

Interfejs po angielsku z polskimi kategoriami w środku to osobna decyzja: wymaga nazw
wielojęzycznych w schemacie dokumentu.

---

## 5. Architektura wersji anglojęzycznej

### Pytanie źle postawione

„Osobna instancja czy przełącznik?" zakłada, że wszystko jest przełączalne. Interfejs
i rozmowa — tak. **Korpus — nie.** Nie pokaże się niemieckiemu szpitalowi polskich
zarządzeń i nie nazwie tego wersją angielską.

### Fakt, który rozstrzyga sprawę

**Czat już respektuje uprawnienia do folderów.** Backend wylicza `allowedFolderIds`
z ról konta i przekazuje je do n8n, który filtruje po nich Qdranta
(`backend/app/chat/router.py`, filtr po `metadata.folder_id`). Konto widzi w czacie
wyłącznie dokumenty z folderów, do których ma dostęp.

### Rekomendacja: jedna instancja demo, dwa korpusy

- angielskie dokumenty w osobnym drzewie folderów,
- rola „Demo EN" z dostępem wyłącznie do nich,
- konto demo z językiem interfejsu i odpowiedzi ustawionym na angielski.

Z perspektywy oglądającego **wszystko jest po angielsku** — interfejs, dokumenty,
odpowiedzi. Nic polskiego nie jest widoczne. Konto polskie widzi dzisiejsze demo.

Przewagi nad trzecią instancją: brak nowego wdrożenia w rytuale aktualizacji, jeden
obraz i jeden numer wersji, a przy okazji demo pokazuje działający podział uprawnień.

### Kiedy jednak osobna instancja

Przy **prawdziwym kliencie anglojęzycznym**. Jego dane nie mogą dzielić bazy z demo —
ta sama zasada, dla której rozdzielone są ZCO i HiRS.

### Co trzeba poprawić przy angielskim korpusie w tej samej instancji

| Problem | Skutek | Koszt |
|---|---|---|
| Generator streszczeń ma polski prompt | streszczenia angielskich dokumentów po polsku; a streszczenia są magnesem wyszukiwania | 1 dzień |
| Schematy dokumentów wspólne dla instancji, z polskimi nazwami | trzeba dołożyć schematy angielskie obok; rejestr staje się dwujęzyczny | 0,5 dnia |
| 69 polskich słów pomijanych w doborze fragmentów | „the", „for", „and" nie są odfiltrowywane | mierzalne, niekrytyczne |
| Pięcioznakowy rdzeń słowa (polska fleksja) | dla angielskiego prawie nieszkodliwy (brak fleksji); dla niemieckich złożeń i alfabetów niełacińskich bez sensu | zob. poziom 2 |

---

## 6. Poziomy dojrzałości językowej

**Poziom 0 — dzisiaj.** Język odpowiedzi przypadkowy. Model bywa dobry, ale nie da się
tego obiecać klientowi.

**Poziom 1 — język jawny (2–3 dni).** Aplikacja ustala język odpowiedzi i przekazuje go
do promptu jako parametr, zamiast liczyć na nakaz „odpowiadaj po polsku". Do tego
znaczniki niezależne od języka. Wyszukiwanie bez zmian — bge-m3 działa międzyjęzykowo.

> Uwaga o „wyłamywaniu się" modelu z nakazu: to nie kaprys. Model dostaje polską
> instrukcję, polskie fragmenty i pytanie po angielsku. Instrukcja mówi jedno, całe
> wejście drugie. **Nie wzmacniać nakazu — usunąć konflikt**, podając język jawnie.

**Poziom 2 — dobór fragmentów świadomy języka (1 tydzień + pomiary).** Lista słów
pomijanych i sposób porównywania rdzeni dobierane wg rozpoznanego języka. Warunek
konieczny: zestaw kontrolny per język.

**Poziom 3 — zbiór wielojęzyczny (tygodnie).** Dokumenty w wielu językach w jednej
bazie: rozpoznanie języka per dokument, streszczenia w dwóch językach, schematy
z nazwami wielojęzycznymi, ocena jakości dla każdej pary język-pytania × język-dokumentu.
To projekt, nie zadanie.

---

## 7. Plan dojścia do dema anglojęzycznego

| Krok | Zakres | Koszt |
|---|---|---|
| 1 | Znaczniki cytowania i odmowy niezależne od języka | 0,5 dnia |
| 2 | Interfejs EN (next-intl) + wybór języka w Profilu | ~1 tydzień |
| 3 | Jawny język odpowiedzi przekazywany do promptu | wliczone w krok 2 |
| 4 | Korpus EN na demo: foldery, rola, konto, język streszczeń | 2–3 dni |
| 5 | Zestaw kontrolny pytań po angielsku | 1 dzień |

Razem około dwóch tygodni pracy programistycznej. **Najdłuższy element leży poza kodem:**
skąd wziąć wiarygodny zestaw angielskich dokumentów szpitalnych. Bez nich reszta nie ma
czego pokazywać.

---

## 8. Warunek, od którego nie ma odstępstwa

**Nie da się stwierdzić, czy jakość odpowiedzi w danym języku jest akceptowalna, dopóki
nie powstanie zestaw kontrolny pytań w tym języku.** Dziś mamy 24 pytania kontrolne,
wszystkie polskie (`backend/app/retrieval_bench_pytania.json`, uruchamiane przez
`retrieval_bench.py`).

Ta sama zasada dwukrotnie w sierpniu 2026 uchroniła projekt przed „poprawkami", które
po pomiarze okazały się pogarszać wyniki — deduplikacją bliźniaczych fragmentów
i streszczeniami sekcyjnymi. Obie wyglądały rozsądnie na papierze.

Wniosek dla rozmów handlowych: **wielojęzyczność interfejsu można obiecać z datą.
Jakości odpowiedzi w nowym języku — dopiero po pomiarze.**
