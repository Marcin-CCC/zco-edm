# Rozbudowa w kierunku agentów

Dokument planistyczny z **17 sierpnia 2026**. Ocena pomysłu na agenta zgodności
akredytacyjnej, pomiar wykonalności najtrudniejszego etapu oraz lista kolejnych agentów.

Dokumenty pokrewne: [`analiza-wielojezycznosc.md`](analiza-wielojezycznosc.md),
[`analiza-unsloth.md`](analiza-unsloth.md).

---

## 1. Czym jest, a czym nie jest dzisiejszy „agent"

Ekran **Wyszukiwanie** bywa nazywany mechanizmem agentowym. To nie jest ścisłe: pytanie
po polsku wchodzi, struktura filtra wychodzi, koniec. Jedno wywołanie modelu z wymuszonym
schematem odpowiedzi — **użycie narzędzia, nie agent**. Nie ma pętli, planowania kroków
ani weryfikacji własnego wyniku.

Rozróżnienie ma znaczenie kosztowe. Przejście od jednego wywołania do pętli z weryfikacją
wymaga trzech rzeczy, których aplikacja jeszcze nie ma:

- **infrastruktury zadań długotrwałych** z postępem i możliwością przerwania,
- **miejsca na wyniki** (raporty jako byt w bazie, nie tylko wiadomość w czacie),
- **ekranu do zatwierdzania przez człowieka** — agent proponuje, człowiek przyjmuje.

To wspólna podbudowa pod wszystkie agenty. Przy pierwszym z nich trzeba ją zbudować raz
i policzyć jej koszt osobno od samego agenta.

---

## 2. Agent oceny zgodności akredytacyjnej

### 2.1. Dlaczego czat sobie z tym nie poradzi

Przyczyna jest głębsza niż długość dokumentu. **Ocena zgodności to pytanie o kompletność,
a wyszukiwanie semantyczne odpowiada na pytanie o podobieństwo.**

RAG zwróci fragmenty najbardziej podobne do tego, co procedura zawiera. W audycie
najcenniejsze jest to, czego procedura **nie** zawiera — a brakujący wymóg nie ma do czego
być podobny, więc nigdy nie trafi do kontekstu. **Wyszukiwanie po podobieństwie jest
strukturalnie niezdolne do znalezienia nieobecności.** Zwiększanie liczby fragmentów tego
nie zmieni.

Wniosek: nie budować tego jako lepszego RAG-u nad dokumentem akredytacyjnym.

### 2.2. Co pokazał pomiar dokumentu

Dokument `standardy-akredytacyjne-szpitale-2025.pdf` (1015 kB, 310 fragmentów w bazie
wektorowej, 5% całego zbioru) **nie jest prozą — to baza danych wydrukowana jako PDF**:

```
DO 3  PACJENCI SĄ OBJĘCI OCHRONĄ RADIOLOGICZNĄ (STANDARD MOŻE BYĆ WYŁĄCZONY).
1.  Opis wymagań
    Szpital powinien: zapewnić środki chroniące…; stosować je adekwatnie…
    Co najmniej 60% stanowi 8 kamieni milowych.
    Waga standardu - 0,25
```

Zmierzone w sparsowanym tekście (533 kB):

| Element | Liczba |
|---|---|
| „Waga standardu" | **223** |
| „Opis wymagań" | 226 |
| „STANDARD OBLIGATORYJNY" | 15 |
| „MOŻE BYĆ WYŁĄCZONY" | 67 |
| wzmianki o kamieniach milowych | 151 |

Czyli około **223 standardy**, każdy z wagą, częścią z nich obligatoryjną, częścią
wyłączalną, z progami procentowymi przy kamieniach milowych.

### 2.3. Kluczowe ustalenie: to w 90% nie jest zadanie dla modelu

Pytanie „czy Qwen poradzi sobie z konwersją dokumentu na tabelę" jest źle postawione,
bo **nikomu — ani modelowi, ani człowiekowi — nie należy podawać 533 kB naraz.**

Struktura jest na tyle regularna, że rozkłada się deterministycznie. Test: jedno wyrażenie
regularne, napisane za pierwszym podejściem, znalazło **214 z ~223 standardów (96%)**,
a 191 z tych bloków zawierało wagę w swoim zakresie. Godzina dostrajania dociągnie to
do kompletu.

Właściwy podział pracy wygląda więc tak:

1. **Skrypt** dzieli dokument na ~223 bloki po około 2 kB — deterministycznie, powtarzalnie,
   bez modelu.
2. **Model** dostaje pojedynczy blok i wymuszony schemat odpowiedzi. To dokładnie to samo
   zadanie, które `doc_extract` już dziś wykonuje na dokumentach klienta — tyle że na
   krótszym i bardziej regularnym tekście.
3. **Człowiek** przegląda gotowy rejestr raz.

Przy takim podziale wątpliwość „czy model to udźwignie" znika: model nigdy nie widzi
więcej niż jednego standardu.

### 2.4. Jedna realna komplikacja: zgubione kody standardów

W sparsowanym tekście kody (`CO 3`, `PP 12`) zachowały się przy **41 z 223 standardów**.
Reszta ich nie ma — parser nie wciągnął elementu układu strony, w którym siedzą.

To ma znaczenie praktyczne: **audytorzy rozmawiają kodami**, więc rejestr bez kodów będzie
kulawy. Wniosek: źródłem rejestru ma być **oryginalny PDF**, a nie fragmenty z bazy
wektorowej. Fragmenty są przystosowane do wyszukiwania, nie do odtwarzania struktury.

### 2.5. Jak zbudować samego agenta

**Rejestr standardów** — jednorazowo, tabela: kod, dział, tytuł, obligatoryjny, waga,
lista wymagań, kamienie milowe, próg. Rejestr jest stabilny; standardy zmieniają się
co kilka lat, nie co tydzień.

**Pętla po standardach, nie jedno pytanie.** Agent wybiera standardy dotyczące danej
procedury i dla **każdego z osobna** zadaje małe, sprawdzalne pytanie: oto wymagania
standardu, oto procedura — co jest spełnione, co nie, a czego nie da się rozstrzygnąć.
Jedno niemożliwe pytanie zamienia się w kilkadziesiąt możliwych, każde z uzasadnieniem
i cytatem.

**Trzy stany, nie dwa.** „Nie da się rozstrzygnąć" musi być dozwoloną odpowiedzią.
Pytanie tak/nie zmusza model do zgadywania tam, gdzie materiał nie wystarcza — ten sam
problem, który w czacie rozwiązała reguła „brak informacji ≠ brak ograniczenia".

**Punktacja liczona w kodzie.** Wagi i progi są w rejestrze, więc wynik liczymy
arytmetycznie. Modele mylą się w rachunkach i nie ma powodu im tego zlecać.

**Raport do przejrzenia, nie werdykt.** Wynik jako dokument (mamy eksport do arkusza),
z podziałem spełnione / niespełnione / do rozstrzygnięcia, każde z cytatem. Materiał
dla działu jakości, nie orzeczenie.

### 2.6. Koszt, ryzyka i warunek startu

**Koszt:** 2–3 tygodnie, z czego istotna część to wspólna podbudowa z punktu 1.

**Warunek, bez którego bym nie zaczynał:** 3–5 procedur ocenionych wcześniej przez dział
jakości szpitala, jako wzorzec do porównania. Bez tego nie da się stwierdzić, czy agent
ocenia dobrze — ta sama zasada, która w sierpniu dwukrotnie uchroniła projekt przed
pogorszeniem wyników.

**Ryzyka:**

- *Konfabulacja przy niedomiarze materiału* — łagodzona trzema stanami i wymogiem cytatu.
- *Zakres odpowiedzialności* — raport jest wsparciem decyzji, nie certyfikacją; musi to
  mówić wprost.
- *Czas przetwarzania* — 42 procedury × kilkadziesiąt standardów to zadanie wsadowe,
  nie interaktywne. Wpisuje się w istniejący wzorzec kolejki, ale nie w czat.

---

## 3. Pozostali agenci, uszeregowani

**Agent uzupełniania metadanych — najtańszy, zacząć od niego.** W Kolejce plików widać
dokumenty, z których nie udało się wyciągnąć pól. Agent wraca do nich z innym podejściem
i **proponuje wartości do zatwierdzenia**. Poprawia bezpośrednio jakość wyszukiwarki po
polach, ma oczywistą miarę sukcesu (ile pól uzupełniono i ile człowiek zaakceptował)
i buduje podbudowę, której potrzebuje agent zgodności. Kilka dni.

**Agent spójności zbioru.** Szuka dokumentów mówiących co innego o tym samym: zarządzenie
i załącznik z inną kwotą, dwie wersje regulaminu z różnymi terminami. Mamy udokumentowane
[25 grup duplikatów](duplikaty-dokumentow-20260816.md) i pamiętamy rodzinę ZFŚS, w której
zlanie dwóch dokumentów popsuło odpowiedzi. Łączy się z odłożonym tematem relacji między
dokumentami.

**Agent przeglądu okresowego.** Dokumenty powołujące się na nieobowiązujące akty,
nieaktualizowane od lat, mające następcę oznaczonego jako „tekst jednolity". Wersja tania
jest czysto regułowa na polach opisowych; droga wymaga czytania treści pod kątem klauzul
uchylających.

**Agent wyciągu tematycznego.** „Zbierz wszystkie zasady dotyczące pracy zdalnej ze
wszystkich obowiązujących dokumentów" — inaczej niż czat, bo ma być **wyczerpujący**,
nie trafny, i produkuje dokument z przypisami.

**Agent odpowiedzi na wnioski i skargi.** Projekt pisma z powołaniem na wewnętrzne
regulacje. Wysoka wartość, najwyższe ryzyko — to wychodzi na zewnątrz szpitala.

---

## 4. Wyszukiwanie w sieci

Tylko dla wdrożeń z dostępem do internetu — ale z mocniejszym zastrzeżeniem, niż wynika
z samej dostępności. Najsilniejszym argumentem sprzedażowym jest dziś zdanie, że **treść
dokumentów nie opuszcza serwera**. Wyszukiwanie w sieci tę obietnicę narusza, bo do
zapytania trzeba wysłać fragment pytania użytkownika.

Jeśli wdrażać, to jako **osobny, wyraźnie oznaczony tryb**, nigdy jako domyślne
uzupełnienie odpowiedzi z dokumentów wewnętrznych, z rozdzielonymi źródłami w wyniku.
Użytkownik musi wiedzieć, czy patrzy na cytat z regulaminu szpitala, czy na coś z sieci.

Przy standardach akredytacyjnych ma to sens jako **sprawdzenie aktualności rejestru**
(standardy są publiczne i bywają nowelizowane), a nie jako źródło ocen.

---

## 5. Proponowana kolejność

| | Zadanie | Koszt |
|---|---|---|
| 1 | Podbudowa: zadania długotrwałe, wyniki, ekran zatwierdzania | wliczona w pierwszego agenta |
| 2 | Agent uzupełniania metadanych | kilka dni |
| 3 | Rejestr standardów akredytacyjnych (skrypt + model + przegląd) | 2–3 dni |
| 4 | Agent zgodności na bazie rejestru | 2 tygodnie |
| 5 | Pozostali agenci wg potrzeb klienta | — |

Punkt 3 da się zacząć od razu i niezależnie: rejestr jest wartościowy sam w sobie
(przeszukiwalna tabela standardów), nawet zanim powstanie agent, który go użyje.
