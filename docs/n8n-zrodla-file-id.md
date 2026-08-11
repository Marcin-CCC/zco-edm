# Źródła odpowiedzi mają nieść `file_id`, nie samą nazwę pliku

Przepływ: **ZCO - RAG do testowania EDM ZCO** (`4Hi4ExPUVEh8U2xX`), węzeł **Chunks Filter**.
Dwie zmiany w jednym miejscu — jeden Publish.

## Dlaczego

Nazwa pliku NIE JEST identyfikatorem dokumentu. Zmierzone na bazie ZCO 2026-08-10:
**9 nazw powtarza się i obejmuje 18 dokumentów**. Pod nazwą `1.pdf` leżą dwa różne
zarządzenia:

| file_id | dokument | fragmenty |
|---|---|---|
| 279 | Zarządzenie **1/2009** | 1 fragment, tylko strona 1 |
| 290 | Zarządzenie **1/2010** | 27 fragmentów, strony 1–14 |

Na pytanie „jak wyceniane jest usunięcie szwów?" odpowiedź powstała ze **strony 4
dokumentu 1/2010** (`Usunięcie szwów — 97.3 — 20,00`), ale cytowanie pokazało
**Zarządzenie 1/2009 (str. 4)** — dokument, który ma jedną stronę. Kliknięcie
odnośnika pobierało niewłaściwy plik.

Przyczyna: n8n przysyła w źródłach tylko `filename` i `page`, więc backend musi
zgadywać, o który dokument chodzi, dopasowując po nazwie. Przy dwóch plikach o tej
samej nazwie zgaduje źle. Payload Qdranta niesie `metadata.file_id` — wystarczy go
przekazać dalej.

Backend jest już przygotowany: gdy dostanie `file_id`, używa go i nazwy nie tyka.
Do czasu tej zmiany źródła o niejednoznacznej nazwie tracą odnośnik (lepiej brak
odnośnika niż odnośnik do innego dokumentu), a w logu pojawia się ostrzeżenie
`[CHAT] Nazwa pliku nie wskazuje jednego dokumentu`.

## Zmiana w węźle „Chunks Filter"

W sekcji **4. Etykiety [Źródło N]** podmień fragment budujący `idByKey` i `sourceById`:

### było

```javascript
  if (filename) {
    const key = `${filename}|${page ?? ""}`;
    if (idByKey[key] === undefined) {
      idByKey[key] = nextId;
      sourceById[nextId] = { filename, page, score: Math.round((c.score ?? 0) * 100) / 100 };
      nextId++;
    }
    id = idByKey[key];
  }
```

### ma być

```javascript
  const fileId = c.md.file_id ?? null;
  if (filename) {
    // Klucz po file_id, nie po nazwie: dwa RÓŻNE dokumenty potrafią nazywać się
    // tak samo („1.pdf" w bazie ZCO), a przy kluczu z nazwy ich fragmenty z tej
    // samej strony scalałyby się w jedno źródło.
    const key = `${fileId ?? filename}|${page ?? ""}`;
    if (idByKey[key] === undefined) {
      idByKey[key] = nextId;
      sourceById[nextId] = {
        filename,
        page,
        file_id: fileId,          // jedyny pewny identyfikator dokumentu
        score: Math.round((c.score ?? 0) * 100) / 100,
      };
      nextId++;
    }
    id = idByKey[key];
  }
```

Zmiany są dwie i obie są potrzebne:

1. **`file_id` w źródle** — backend przestaje zgadywać po nazwie.
2. **klucz z `file_id`** — bez tego fragmenty dwóch różnych dokumentów o tej samej
   nazwie i tej samej stronie nadal scalałyby się w jedną pozycję listy źródeł.
   To ten sam błąd, tylko o poziom wcześniej.


## UWAGA — dwie dalsze zmiany, bez których pierwsza nic nie daje

Sprawdzenie na opublikowanym przepływie (2026-08-11) pokazało, że sam „Chunks Filter"
nie wystarczy. Poniższe dwie poprawki są konieczne.

### A. Węzeł „Sources Gate" GUBI `file_id`

Ten węzeł przepisuje źródła pole po polu i `file_id` w tej liście nie ma — więc do
backendu nadal nie dociera nic poza nazwą. Dopisz jedną linię:

```javascript
  .map((id) => ({
    filename: sourceById[id].filename,
    page: sourceById[id].page,
    file_id: sourceById[id].file_id,      // <-- DOPISAĆ
    score: sourceById[id].score,
    cited: cytowane.has(String(id)),
  }));
```

### B. Fragmenty DOBRANE też potrzebują `file_id`

W sekcji **1b** węzła „Chunks Filter" fragmenty z `extraChunks` dostają metadane bez
identyfikatora. Backend wysyła je od wersji 1.0.21; wystarczy przekazać dalej:

```javascript
  dobrane.push({
    score: scoreThreshold,
    text,
    md: { filename: e.filename, page: e.page, file_id: e.file_id ?? null },
  });
```

Bez tego fragment doklejony przez dobór z dokumentu-zwycięzcy nadal byłby
rozpoznawany po nazwie — czyli dokładnie tak, jak przed całą poprawką.

### Kosmetyka (nieobowiązkowe)

W sekcji 4 komentarz nagłówkowy mówi jeszcze „unikalne po filename|page", choć klucz
jest już po `file_id`. Warto poprawić, bo w tym przepływie komentarze są instrukcją
obsługi, a nie ozdobą.

## Po edycji

Kliknij **Publish** (od n8n 2.34 sam zapis nie wchodzi do ruchu).

## Weryfikacja

Zapytaj: **„jak wyceniane jest usunięcie szwów?"**. Cytowanie ma wskazywać
**Zarządzenie 1/2010, str. 4**, a kliknięcie ma otworzyć plik o 14 stronach.
W logu backendu nie powinno być już ostrzeżenia o niejednoznacznej nazwie.
