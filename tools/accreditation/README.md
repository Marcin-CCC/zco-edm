# Rejestr standardów akredytacyjnych

Zamienia dokument *Standardy Akredytacyjne — szpitale 2025* (256 stron PDF) na tabelę
standardów gotową do maszynowego użycia.

```bash
python split_standards.py standardy-akredytacyjne-szpitale-2025.pdf standardy-2025.json
```

## Wynik na wydaniu 2025

| | |
|---|---|
| standardów w rejestrze | **210** |
| kodów w spisach działów (źródło prawdy z dokumentu) | 226 |
| z tego nagłówków grup, poprawnie pominiętych | 17 |
| **zgubionych standardów** | **0** |
| działów | 17 |
| obligatoryjnych | 15 |
| wyłączalnych | 62 |
| z pełną rubryką 5/3/1 | 119 |
| z rubryką 5/1 (bez oceny częściowej — tak są zapisane) | 89 |
| bez wagi (do przejrzenia) | 2 |
| suma wag | ok. 119 |

### Skąd wiadomo, że nic nie zginęło

Skrypt **sam się sprawdza** przy każdym uruchomieniu i kończy się błędem, jeśli
znajdzie zgubiony standard. Kontrola nie opiera się na naszym własnym wskaźniku,
tylko na **spisach standardów, które dokument zawiera na stronach tytułowych działów** —
to źródło od nas niezależne.

Każdy kod ze spisu, którego nie ma w rejestrze, jest klasyfikowany:

- **nagłówek grupy** — kod bez własnego „Opisu wymagań", którego treść niosą dzieci
  (`KZ 1` → `KZ 1.1`, `KZ 1.2`…). Takich jest 17 i słusznie nie są rekordami.
- **zgubiony standard** — kod z treścią, którego parser nie złapał. Takich jest 0.

`OS 1.14` jest w rejestrze, choć nie ma go w spisie działu — spis jest w tym miejscu
niekompletny, sam standard ma pełną treść.

### Co świadomie zostaje poza rejestrem (19% znaków dokumentu)

| Fragment | Wielkość | Uwaga |
|---|---|---|
| TERMINY I OKREŚLENIA (słowniczek) | 31 kB | **wart osobnego wyciągnięcia** — definicje przydadzą się agentowi |
| Strona tytułowa, wstęp, historia standardów | 9 kB | bez wartości maszynowej |
| Strony tytułowe i wprowadzenia do działów | ok. 50 kB | spisy standardów i omówienia; spisy służą za kontrolę kompletności |

Żaden z tych fragmentów nie zawiera treści standardu — sprawdzone audytem pokrycia
znak po znaku.

## Rekord standardu

```json
{
  "kod": "CO 1",
  "dzial": "CO",
  "numer": "1",
  "tytul": "SZPITAL WDROŻYŁ ROZWIĄZANIA SŁUŻĄCE DO ZARZĄDZANIA RUCHEM PACJENTÓW.",
  "obligatoryjny": false,
  "wylaczalny": true,
  "waga": 0.5,
  "wymagania": "W szpitalnym oddziale ratunkowym lub izbie przyjęć opracowano…",
  "sposob_sprawdzenia": "1) przegląd dokumentacji szpitala; 2) wywiad z kierownikiem…",
  "punktacja": {
    "5": "Szpital wdrożył rozwiązania… zgodnie z wymogami standardu.",
    "3": "Szpital w przeważającej części wdrożył… (co najmniej 60% kamieni milowych).",
    "1": "Szpital nie wdrożył rozwiązań…"
  }
}
```

## Dlaczego skrypt, a nie model językowy

Dokument jest **bazą danych wydrukowaną jako PDF**: każdy standard ma ten sam szkielet —
kod, tytuł wersalikami, „Opis wymagań", „Sposób sprawdzenia", „Ocena punktowa" i wagę.
Podział jest więc zadaniem deterministycznym. Model nie jest do niego potrzebny i nie ma
powodu ryzykować, że coś przeinaczy.

Najcenniejsza jest **rubryka punktowa**: dokument sam mówi, co zasługuje na 5, 3 albo
1 punkt. Dzięki temu przyszły agent oceny zgodności nie musi wymyślać kryteriów — jego
zadaniem jest wskazać, który z podanych opisów pasuje do ocenianej procedury. To
klasyfikacja z zamkniętą listą wariantów, a nie otwarty osąd.

## Źródłem musi być oryginalny PDF

Nie fragmenty z bazy wektorowej. Przy nich **kody standardów zachowały się w 41 przypadkach
na 223** — parser dokumentów nie wciągnął elementu układu strony, w którym siedzą.
Fragmenty są przystosowane do wyszukiwania, nie do odtwarzania struktury. Audytorzy
rozmawiają kodami, więc rejestr bez nich byłby bezużyteczny.

## Pułapki, które kosztowały czas przy pisaniu

Wszystkie dawały **cichy zły wynik zamiast błędu** — stąd wbudowana samokontrola.

- **Filtr nagłówka strony zjadał rubrykę punktową.** Pierwsza wersja usuwała każdą linię
  będącą samą liczbą — a oceny 5, 3 i 1 stoją w osobnych wierszach i wyglądają dokładnie
  jak numer strony. Różni je tylko położenie, więc nagłówek odcinamy wyłącznie z początku
  strony. Objaw: zero standardów z rubryką przy poprawnej reszcie.
- **Kody bywają hierarchiczne** (`OS 1.2`, `LA 2.1`). Wzorzec dopuszczający tylko liczbę
  całkowitą zwijał cały dział Ocena Stanu Zdrowia do jednego standardu — 140 zamiast 208.
- **W dziale PAT kod jest rozbity na dwie linie** (`PAT` / `2.2`). Bez scalenia cztery
  standardy patomorfologii wypadały razem z całą treścią, a kontrola pokazywała je jako
  „nagłówki grup" — czyli fałszywie uspokajała.
- **Definicją standardu jest „Opis wymagań", nie waga.** Wcześniejsza wersja wymagała wagi
  i myliła się w obie strony: nagłówki grup wpadały do rejestru przypadkiem, a standardy
  bez wagi wypadały mimo pełnej treści.
- **Zakres kodu liczymy do NASTĘPNEGO kodu**, nie „kilkanaście linii w przód". Inaczej
  nagłówek grupy zagarnia „Opis wymagań" należący do swojego pierwszego dziecka —
  na tym błędzie kontrola dała wynik dokładnie odwrotny do prawdy.
- **Numer standardu zostaje napisem**, nie liczbą; `int("1.2")` się wywraca.

## Następny krok

Rejestr jest wartościowy sam w sobie — to przeszukiwalna tabela 208 standardów z wagami
i progami. Do agenta oceny zgodności potrzebny jest jeszcze podział pola `wymagania`
(dziś proza) na listę pojedynczych, sprawdzalnych wymogów. **To** jest zadanie dla modelu:
jeden standard na wywołanie, wymuszony schemat odpowiedzi — czyli dokładnie to, co
`backend/app/doc_extract.py` robi dziś na dokumentach klienta.

Zob. [`docs/analiza-agenty.md`](../../docs/analiza-agenty.md).
