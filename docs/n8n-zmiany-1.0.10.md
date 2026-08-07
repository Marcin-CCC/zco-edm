# Zmiany w n8n do wersji 1.0.10 — czat ZCO

Przepływ: **ZCO - RAG do testowania EDM ZCO** (`4Hi4ExPUVEh8U2xX`).
Obie zmiany są w JEDNYM przepływie, więc wystarczy **jeden Publish** na końcu.

> Po zapisaniu koniecznie kliknij **Publish** — od n8n 2.34 zapis w edytorze
> nie wchodzi do ruchu. Weryfikacja: `versionId` musi być równy `activeVersionId`.

---

## Zmiana 1 — reguła „brak informacji ≠ brak ograniczenia"

**Węzeł:** `AI Agent` → `Options` → `System Message`.

W sekcji `## ZASADA NADRZĘDNA: odpowiadaj TYLKO z Kontekstu` dopisz **na końcu
listy punktowanej** (po punkcie o „Dotychczasowej rozmowie") jeden nowy punkt:

```
- Brak informacji w Kontekście NIE JEST dowodem, że dana zasada nie istnieje. Jeśli nie znajdujesz warunku, terminu, limitu ani ograniczenia, napisz WPROST, czego nie znalazłeś (np. „w dostępnych fragmentach nie ma zapisu o wieku"). Zdania w rodzaju „nie jest to ograniczone", „nie ma takiego wymogu", „przepisy tego nie przewidują", „nie jest bezpośrednio określone" wolno Ci napisać WYŁĄCZNIE wtedy, gdy Kontekst stwierdza to wprost. Nigdy nie wyprowadzaj ich z tego, że czegoś nie widzisz.
```

**Po co:** na pytanie „w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?"
model odpowiedział, że *„wiek nie jest bezpośrednio ograniczony w dokumentach"* —
a jest, w § 12 tego samego regulaminu. To nie było zmyślenie faktu, tylko wniosek
wyciągnięty z nieznalezienia. Ta reguła zamienia złą odpowiedź w uczciwą lukę
i działa na każde pytanie, nie tylko na ten przypadek.

---

## Zmiana 2 — doklejanie fragmentów dobranych przez backend

**Węzeł:** `Chunks Filter` (Code). Zamień **całą** zawartość pola `jsCode`
na poniższy kod. Różnice wobec obecnej wersji: nowa sekcja `1b`, przebudowana
sekcja `3`. Reszta bez zmian.

```javascript
const items = $input.all();
const hook = $('Webhook').first().json.body || {};
// Pytanie zawężone do wskazanych dokumentów → próg wyłączony. Wewnątrz jednego
// dokumentu trafności są z natury niższe (zmierzone 0,33–0,50), a ryzyko odpowiedzi
// z przypadkowego dokumentu nie istnieje, bo zakres ustalił użytkownik.
const scoreThreshold = hook.scopedToFiles === true ? 0 : 0.50;
const maxContextChars = 14000;

// 1. Kandydaci
const candidates = [];
for (const item of items) {
  const doc = item.json.document || item.json;
  if (!doc) continue;
  const score =
    item.json.score !== undefined ? item.json.score :
    doc.score       !== undefined ? doc.score       : 1.0;
  let text = (doc.pageContent || "").replace(
    /data:image\/[a-zA-Z]*;base64,[^\s"']+/g,
    "[USUNIĘTO ELEMENT GRAFICZNY ZE WZGLĘDU NA OCHRONĘ KONTEKSTU]"
  );
  if (!text.trim()) continue;
  candidates.push({ score, text: text.trim(), md: doc.metadata || {} });
}

// 1b. Fragmenty DOBRANE przez backend z dokumentu-zwycięzcy.
// Pytanie o złożonym ciągu rozumowania („w jakim wieku dzieci mogą korzystać
// z wczasów pod gruszą?") ma odpowiedź w tym samym dokumencie, ale na innej
// stronie i z trafnością POD progiem (zmierzone: 0,411 wobec pasma 0,48–0,60
// fragmentów przyjętych). Backend wskazuje takie fragmenty świadomie — po
// sprawdzeniu, że dokument jest rozpoznany jednoznacznie i że brakuje dokładnie
// jednego wątku z pytania — więc próg ich nie dotyczy (zob. app/chat/dobor.py).
const dobrane = [];
for (const e of (hook.extraChunks || [])) {
  const text = (e.text || "").trim();
  if (!text) continue;
  dobrane.push({
    score: scoreThreshold,
    text,
    md: { filename: e.filename, page: e.page },
  });
}

// 2. Wybór po progu. BEZ fallbacku: gdy nic nie przekracza progu, kontekst zostaje
// pusty → model odpowiada „nie znaleziono", a Sources Gate nie ma czego cytować.
candidates.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
let selected = candidates.filter(c => c.score >= scoreThreshold);

// 3. Budżet kontekstu (okno modelu). Fragmenty dobrane mają zagwarantowane miejsce
// — bez tego obcinanie usuwałoby dokładnie to, po co je dobrano. W zamian nie wolno
// im zająć więcej niż połowy kontekstu: pierwszeństwo ma materiał, który przeszedł
// próg trafności. Wypadają wtedy fragmenty NAJSŁABSZE, bo lista jest posortowana.
{
  const dlugosc = (c) => c.text.length + 40;
  const limitDobranych = Math.floor(maxContextChars / 2);
  const zmieszczoneDobrane = [];
  let accDobrane = 0;
  for (const c of dobrane) {
    if (zmieszczoneDobrane.length > 0 && accDobrane + dlugosc(c) > limitDobranych) break;
    zmieszczoneDobrane.push(c);
    accDobrane += dlugosc(c);
  }

  const budgeted = [];
  let acc = 0;
  for (const c of selected) {
    if (budgeted.length > 0 && acc + dlugosc(c) + accDobrane > maxContextChars) break;
    budgeted.push(c);
    acc += dlugosc(c);
  }

  // Kolejność w kontekście zostaje trafnościowa; dobrane mają score równy progowi,
  // więc trafiają na koniec i nie wypierają mocniejszych fragmentów.
  selected = budgeted.concat(zmieszczoneDobrane);
  selected.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

// 4. Etykiety [Źródło N] + mapa id -> źródło (unikalne po filename|page)
const idByKey = {};
const sourceById = {};
let nextId = 1;
let cleanContext = "";
for (const c of selected) {
  const filename = c.md.filename;
  const page = c.md.page ?? null;
  let id = null;
  if (filename) {
    const key = `${filename}|${page ?? ""}`;
    if (idByKey[key] === undefined) {
      idByKey[key] = nextId;
      sourceById[nextId] = { filename, page, score: Math.round((c.score ?? 0) * 100) / 100 };
      nextId++;
    }
    id = idByKey[key];
  }
  cleanContext += (id ? `[Źródło ${id}]\n` : "") + c.text + "\n\n---\n\n";
}
if (!cleanContext.trim()) {
  cleanContext = "Brak wystarczająco dokładnych dokumentów w bazie danych dla tego zapytania.";
}

return [{
  json: {
    context: cleanContext,
    sourceById,
    requestId: hook.requestId || null,
    sources_update_url: hook.sources_update_url || null,
  },
}];
```

---

## Weryfikacja po Publish

1. Nowy wątek czatu, pytanie: **„w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?"**
   Oczekiwane: odpowiedź o przedziale **od 5 do 18 lat** ze wskazaniem
   `Regulamin ZFŚS` (a nie dokumentu ubezpieczeniowego).
2. Pytania kontrolne, które muszą działać **tak jak dotąd**:
   „na co mogą iść środki z ZFŚS?", „jak rozliczyć delegację?",
   „w jakim wieku dzieci uprawnione są do korzystania z ZFŚS?".
3. Pytanie o temat spoza bazy (np. „ile wynosi kara za spóźnioną ewakuację jednorożca?")
   — musi nadal padać czysta odmowa. Dobór jest tam wyłączony z założenia:
   przy pustym kontekście backend nie wysyła żadnych fragmentów.

W logach backendu przy działającym doborze pojawia się wpis:
`[CHAT-DOBOR] 'wieku Zarządzenie i Regulamin ZFŚS' → doklejam 3 fragm. z pliku 203: str. [4, 13, 5]`
