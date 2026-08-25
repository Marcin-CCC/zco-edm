# n8n — zmiany do kroku 1 wielojęzyczności (znaczniki niezależne od języka)

Dotyczy workflow **`ZCO - RAG do testowania EDM ZCO`** (id `4Hi4ExPUVEh8U2xX`), jedynego
aktywnego workflow czatu. Odpowiada na pytania z **obu** wdrożeń — ZCO DM i HiRS —
bo różni je tylko kolekcja Qdranta przekazana w treści żądania.

**Kolejność ma znaczenie.** Najpierw obie aplikacje muszą chodzić na 1.5.21 (kod rozumie
obie postacie znaczników), dopiero potem „Publish" w n8n. Odwrotnie byłoby źle:
odpowiedzi z nowymi znacznikami trafiłyby do starego kodu, który ich nie rozpoznaje.
Sam kod 1.5.21 na starym workflow działa jak dotąd — dlatego wdrożenie może spokojnie
poczekać na dogodny moment.

Zmian jest trzy, w trzech nodach. Po wszystkich trzech naraz — **Publish**.
Od n8n 2.34 sam zapis w edytorze nie wchodzi do ruchu.

---

## 1. Node „Chunks Filter" — etykiety fragmentów w Kontekście

Sekcja `// 4. Etykiety…`, blisko końca kodu. Do podmiany są **dwie linijki**.

Znajdź:

```js
// 4. Etykiety [Źródło N] + mapa id -> źródło (unikalne po filename|page)
```

zamień na:

```js
// 4. Etykiety [[N]] + mapa id -> źródło (unikalne po filename|page)
```

Znajdź (kilkanaście linijek niżej, w pętli `for (const c of selected)`):

```js
  cleanContext += (id ? `[Źródło ${id}]\n` : "") + c.text + "\n\n---\n\n";
```

zamień na:

```js
  cleanContext += (id ? `[[${id}]]\n` : "") + c.text + "\n\n---\n\n";
```

*Po co:* model odwzorowuje w odpowiedzi tę postać etykiety, którą widzi w Kontekście.
Zostawienie tu polskiego słowa ciągnęłoby go z powrotem do „[Źródło N]".

---

## 2. Node „AI Agent" → opcja **System Message** — dwa akapity

### 2a. Odmowa

W sekcji `## ZASADA NADRZĘDNA: odpowiadaj TYLKO z Kontekstu` znajdź punkt zaczynający
się od „Jeśli w Kontekście NIE MA informacji" i zamień **cały ten punkt** na:

```
- Jeśli w Kontekście NIE MA informacji potrzebnej do odpowiedzi, Twoja CAŁA odpowiedź to dokładnie: [[BRAK]] i nic więcej — bez zdania wyjaśniającego, bez przeprosin, bez tłumaczenia tego znacznika na jakikolwiek język. Jeśli natomiast informacje SĄ — udziel odpowiedzi i pod ŻADNYM pozorem nie doklejaj [[BRAK]] na końcu.
```

### 2b. Cytowanie źródeł

Zamień **całą sekcję** `## Cytowanie źródeł (OBOWIĄZKOWE)` — od nagłówka do ostatniego
punktu, tuż przed `## Kontekst z bazy danych` — na:

```
## Cytowanie źródeł (OBOWIĄZKOWE)

- Każdy fragment Kontekstu jest poprzedzony znacznikiem „[[N]]", gdzie N to numer źródła.
- Za każdym zdaniem lub punktem opartym na danym fragmencie dodaj znacznik [[N]] — dokładnie w tym formacie: PODWÓJNE nawiasy kwadratowe i sama liczba, bez żadnego słowa (np. „...w terminie 7 dni roboczych [[1]].").
- Znacznik wygląda identycznie niezależnie od języka, w którym odpowiadasz. Nigdy go nie tłumacz ani nie zastępuj słowem („Źródło", „Source", „Quelle").
- Jeśli zdanie opiera się na kilku fragmentach, wypisz numery po przecinku w jednym znaczniku: [[2, 5]].
- Używaj wyłącznie numerów, które faktycznie wykorzystałeś. Nie wymyślaj numerów, nie podawaj nazw plików.
- NIE twórz osobnej listy źródeł na końcu — zestawienie powstaje automatycznie.
- Przy odpowiedzi grzecznościowej lub gdy nie korzystasz z żadnego fragmentu — nie dodawaj żadnych znaczników.
```

Reszty promptu nie ruszamy.

---

## 3. Node „Sources Gate" — rozpoznawanie cytowań i odmowy

### 3a. Wyłuskiwanie numerów

Znajdź na początku kodu:

```js
// Numery przywołane przez model w treści: [Źródło 3], (Źródło 1), [[Źródło 2]] ...
const cytowane = new Set();
const re = /Źródło\s*(\d+)/gi;
let m;
while ((m = re.exec(answer)) !== null) cytowane.add(m[1]);
```

zamień na:

```js
// Numery przywołane przez model. Obie postacie naraz: neutralna [[3]] / [[2, 5]]
// i dawna [Źródło 3] — prompt zmienia człowiek, więc przez chwilę mogą chodzić obie.
const cytowane = new Set();
const re = /\[\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]\]|Źród(?:ło|ła)\s*(\d+(?:\s*,\s*\d+)*)/gi;
let m;
while ((m = re.exec(answer)) !== null) {
  for (const n of (m[1] ?? m[2] ?? '').split(',')) {
    const nr = n.trim();
    if (nr) cytowane.add(nr);
  }
}
```

### 3b. Zerowanie źródeł przy odmowie

Znajdź pod koniec kodu:

```js
// Czysta odmowa jako CAŁA odpowiedź → nie pokazujemy żadnych źródeł
const NO_ANSWER = 'Niestety, nie znaleziono w dokumentach informacji na ten temat.';
if (answer.replace(/\s+/g, ' ').trim() === NO_ANSWER) sources = [];
```

zamień na:

```js
// Czysta odmowa jako CAŁA odpowiedź → nie pokazujemy żadnych źródeł.
// Znacznik jest niezależny od języka; stare zdanie zostaje dla rozmów sprzed zmiany.
const ODMOWY = [
  '[[BRAK]]',
  'Niestety, nie znaleziono w dokumentach informacji na ten temat.',
];
if (ODMOWY.includes(answer.replace(/\s+/g, ' ').trim())) sources = [];
```

---

## Po „Publish" — co sprawdzić

| Pytanie | Czego oczekujemy |
|---|---|
| Zwykłe pytanie po polsku, na które są dokumenty | odpowiedź jak dotąd, odnośniki w treści klikalne, użyte źródła podświetlone |
| Pytanie o coś, czego w dokumentach nie ma | zdanie „Niestety, nie znaleziono…", lista źródeł **pusta** |
| „Cześć" | krótka odpowiedź, żadnych znaczników, brak źródeł |
| To samo pytanie merytoryczne po angielsku | odnośniki są (dziś bez zmiany promptu znikały) |

Znacznika `[[BRAK]]` ani `[[1]]` użytkownik nie powinien zobaczyć nigdzie —
interfejs podmienia pierwszy na zdanie, a drugi na odnośnik.

## Gdyby coś poszło nie tak

W n8n: **History** przy workflow → przywrócenie poprzedniej wersji → Publish.
Po stronie aplikacji nic cofać nie trzeba, bo 1.5.21 rozumie też starą postać.
