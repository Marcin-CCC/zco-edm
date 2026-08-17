# Rejestr standardów akredytacyjnych

Zamienia dokument *Standardy Akredytacyjne — szpitale 2025* (256 stron PDF) na tabelę
standardów gotową do maszynowego użycia.

```bash
python split_standards.py standardy-akredytacyjne-szpitale-2025.pdf standardy-2025.json
```

## Wynik na wydaniu 2025

| | |
|---|---|
| standardów | **208** (z 210 znaczników „Waga standardu" w dokumencie) |
| działów | 17 — BP, CO, DO, FA, IM, JO, JZ, KZ, LA, LŻ, OP, OS, PAT, PJ, PP, ZZ, ZŻ |
| obligatoryjnych | 15 |
| wyłączalnych | 61 |
| z pełną rubryką 5/3/1 | 119 |
| z rubryką 5/1 (bez oceny częściowej) | 87 |
| **do przejrzenia ręcznie** | **3** — `LA 2.1`, `ZŻ 3.1`, `ZZ 3` |
| suma wag | 119,25 (wagi: 0,25 / 0,5 / 0,75 / 1,0) |

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

- **Filtr nagłówka strony zjadał rubrykę punktową.** Pierwsza wersja usuwała każdą linię
  będącą samą liczbą — a oceny 5, 3 i 1 stoją w osobnych wierszach i wyglądają dokładnie
  jak numer strony. Różni je tylko położenie, więc nagłówek odcinamy wyłącznie z początku
  strony. Objaw: 0 standardów z rubryką, przy poprawnej reszcie.
- **Kody bywają hierarchiczne** (`OS 1.2`, `LA 2.1`). Wzorzec dopuszczający tylko liczbę
  całkowitą zwijał cały dział Ocena Stanu Zdrowia do jednego standardu — 140 zamiast 208.
- **Numer standardu zostaje napisem**, nie liczbą; `int("1.2")` się wywraca.
- **Blok kończymy na wadze**, nie na kodzie następnego standardu. Między standardami są
  strony tytułowe działów, które doklejone do poprzedniego zaśmiecały jego rubrykę.

## Następny krok

Rejestr jest wartościowy sam w sobie — to przeszukiwalna tabela 208 standardów z wagami
i progami. Do agenta oceny zgodności potrzebny jest jeszcze podział pola `wymagania`
(dziś proza) na listę pojedynczych, sprawdzalnych wymogów. **To** jest zadanie dla modelu:
jeden standard na wywołanie, wymuszony schemat odpowiedzi — czyli dokładnie to, co
`backend/app/doc_extract.py` robi dziś na dokumentach klienta.

Zob. [`docs/analiza-agenty.md`](../../docs/analiza-agenty.md).
