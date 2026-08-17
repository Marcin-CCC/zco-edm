# Unsloth — co warto podpatrzeć

Research z **17 sierpnia 2026**. Dokument do planowania rozwoju: co Unsloth robi
inaczej niż my, co da się z tego wziąć i czego brać nie należy.

Bratni dokument: [`analiza-wielojezycznosc.md`](analiza-wielojezycznosc.md) — kilka
wniosków się zazębia i są oznaczone odsyłaczem.

---

## 1. Czym Unsloth jest, a czym nie jest

Powszechne (i moje początkowe) skojarzenie: **biblioteka przyspieszająca fine-tuning**
modeli językowych — LoRA/QLoRA, około dwa razy szybciej i mniej pamięci. To nadal jest
rdzeń projektu.

Od niedawna istnieje jednak **Unsloth Desktop / Studio** — lokalna aplikacja, która obok
trenowania modeli ma czat, generowanie obrazów i wideo, wyszukiwanie w sieci, piaskownicę
na kod, obsługę MCP oraz **bazę wiedzy RAG**.

**Kluczowe rozróżnienie przed jakimkolwiek porównaniem:** ich RAG to funkcja poboczna
narzędzia dla **jednego użytkownika na jednym komputerze**. Nasza aplikacja to system
wielodostępny z uprawnieniami do folderów. Część ich decyzji projektowych jest optymalna
u nich i błędna u nas — nie dlatego, że są gorsze, tylko dlatego, że rozwiązują inny problem.

---

## 2. Ich potok, obok naszego

| Element | Unsloth Studio | Nasza aplikacja |
|---|---|---|
| Parser dokumentów | **pymupdf4llm** → Markdown, metadane stron | Docling + model VL |
| Formaty | PDF, DOCX, CSV, JSON, TXT | PDF, DOCX, ODT, XLSX |
| Deduplikacja | **SHA256 per zakres, przy wgrywaniu** | brak |
| Osadzenia | Sentence-Transformers (GPU) albo `llama-server --embedding` z llama.cpp (CPU); backend wybierany automatycznie | bge-m3 przez Ollamę |
| Baza wektorów | **sqlite-vec** — jeden plik SQLite | Qdrant — osobny serwer |
| Warstwa leksykalna | **SQLite FTS5** | własna (`backend/app/chat/lexical.py`) |
| Łączenie wyników | `search_hybrid()` — równoległe zapytanie wektorowe i leksykalne, scalanie z konfigurowalną wagą | plan zakresu → dobór fragmentów → streszczenia jako magnes |
| Cytowania | fragment + numer strony w metadanych | znaczniki w treści + lista źródeł |
| Dodatkowo | **PDF → pary pytanie/odpowiedź**, fine-tuning osadzeń i rerankerów | — |

### Czego nie udało się ustalić

- dokładnych rozmiarów fragmentów i strategii dzielenia (`chunking.chunk_text()`),
- czy stosują **reranking** w samym RAG-u — wspierają fine-tuning `BGE-Reranker-v2-m3`,
  ale to nie dowodzi, że reranker jest w potoku,
- jakości działania w praktyce; **niczego nie testowaliśmy na własnym zbiorze**.

---

## 3. Cztery rzeczy warte podpatrzenia

### 3.1. Deduplikacja skrótem SHA256 przy wgrywaniu — zrobić

**Co robią:** liczą skrót zawartości pliku przy wgrywaniu i odrzucają powtórzenia,
zanim trafią do indeksu.

**Dlaczego to nas dotyczy:** mamy udokumentowany problem — [58 plików w 25 grupach](duplikaty-dokumentow-20260816.md),
w tym 8 prawdziwych powtórzeń tej samej treści pod różnymi nazwami. Duplikaty nie tylko
zajmują miejsce: **psują odpowiedzi**, bo ten sam fragment wygrywa dwa razy i wypycha
z kontekstu inne dokumenty.

**Zakres:** kolumna z sumą kontrolną na tabeli plików, liczenie przy wgrywaniu, ostrzeżenie
z nazwą pliku-bliźniaka zamiast cichego odrzucenia (administrator ma zdecydować, czy to
naprawdę duplikat, czy dwie wersje). Dla istniejącego zbioru — jednorazowe przeliczenie.

**Koszt:** pół dnia. **Ryzyko:** żadne. **Priorytet: najwyższy z tej listy.**

### 3.2. Fine-tuning modelu osadzeń — zmierzyć

**Co robią:** to ich rdzenna kompetencja. Wspierają **dokładnie nasz model — bge-m3** —
a także Qwen3-Embedding, E5, EmbeddingGemma i rerankery. Deklarują 1,8–3,3× szybszy
trening niż SentenceTransformers z Flash Attention 2 i 20% mniej pamięci.

**Dlaczego to nas dotyczy:** mamy odłożony problem żargonu. Słownik „grusza → wczasy pod
gruszą" zmierzyliśmy jako **działający (0,501 → 0,620)**, ale odłożyliśmy przez koszt
utrzymania listy. Fine-tuning odwraca zależność: żargon zostaje **wtrenowany w model
osadzeń**, zamiast być listą, którą ktoś musi pielęgnować przy każdym nowym pojęciu.

**Mamy wszystkie składniki:** korpus produkcyjny, 24 pytania kontrolne
(`backend/app/retrieval_bench_pytania.json`), skrypt pomiarowy i GPU na Sparku.

**Zastrzeżenie:** ich dokumentacja podaje przyspieszenie **treningu**, ale **nie podaje
zysku jakościowego**. Nie wiadomo, ile par trzeba i jaki będzie efekt — to trzeba zmierzyć
na własnym zestawie kontrolnym, tak jak mierzyliśmy słownik.

**Koszt:** 2–3 dni na eksperyment z pomiarem. **Ryzyko:** może nie dać zysku — ale koszt
sprawdzenia jest niski, a alternatywa (słownik) jest już zmierzona jako działająca, więc
mamy z czym porównywać.

### 3.3. Szybka ścieżka parsowania — rozważyć po pomiarze

**Co robią:** wybrali pymupdf4llm, czyli parser **5–30× szybszy** od Doclinga, kosztem
jakości: gubi strukturę tabel ze scalonymi komórkami i nagłówkami przez kilka kolumn.

**Dla nas Docling pozostaje właściwym wyborem** — zmierzyliśmy, że tabele mają znaczenie
(stąd trasa ODT przez DOCX, nie przez PDF).

**Ale ich decyzja przypomina o naszym wąskim gardle:** 83% czasu parsowania zjada jeden
etap VL, a przed nami około 1500 dokumentów do przetworzenia. Nie każdy dokument tego
etapu potrzebuje.

**Pomysł:** triaż przy wgrywaniu — PDF z tekstem cyfrowym i bez tabel idzie tanią ścieżką,
skany i dokumenty z tabelami idą przez Docling z VL. Warunek: **najpierw pomiar na próbce**,
ile dokumentów w zbiorze faktycznie kwalifikuje się do taniej ścieżki i czy jakość
odpowiedzi z nich nie spada.

**Koszt:** dzień na pomiar próbki, dopiero potem decyzja o wdrożeniu.

### 3.4. Generowanie par pytanie/odpowiedź z dokumentów — do zestawu kontrolnego

**Co robią:** automatycznie zamieniają dokumenty w zestawy treningowe (PDF, CSV, JSON,
DOCX, TXT → pary Q/A).

**Dla nas ciekawe nie jako trening, tylko jako sposób na zestaw kontrolny.** Z analizy
wielojęzyczności wynika twardy warunek: [nie da się obiecać jakości w nowym języku bez
zestawu kontrolnego w tym języku](analiza-wielojezycznosc.md#8-warunek-od-którego-nie-ma-odstępstwa).
Dziś mamy 24 pytania, wszystkie polskie. Generowanie pytań z dokumentów daje szkielet
takiego zestawu — wymaga ręcznego przeglądu, ale to i tak szybciej niż pisanie od zera
dla każdego języka.

**Koszt:** dzień na potok generujący, plus przegląd wyników.

---

## 4. Czego nie kopiować

**sqlite-vec zamiast Qdranta.** Dla aplikacji jednego użytkownika to eleganckie: cała baza
wiedzy w jednym pliku, zero serwera, zero konfiguracji. U nas odpada — filtrowanie po
`folder_id` na poziomie zapytania wektorowego jest fundamentem podziału uprawnień
(`allowedFolderIds` → filtr Qdranta). To nie wada ich rozwiązania, tylko inny model wdrożenia.

**Ich parsera** — z powodów opisanych w 3.3.

## 5. Gdzie oni są lepsi od nas

**Warstwa leksykalna.** FTS5 z ważonym scalaniem wyników jest **niezależna od języka**,
podczas gdy nasz dobór fragmentów stoi na pięcioznakowych rdzeniach słów i 69 polskich
słowach pomijanych — czyli dokładnie na tym, co zidentyfikowaliśmy jako
[przeszkodę przy wielojęzyczności](analiza-wielojezycznosc.md#6-poziomy-dojrzałości-językowej).
Gdybyśmy przepisywali tę warstwę pod kolejne języki, ich model jest właściwym punktem
odniesienia: równoległe zapytanie leksykalne i wektorowe, jawna waga, brak heurystyk
zależnych od fleksji.

---

## 6. Kolejność, którą proponuję

| | Zadanie | Koszt | Status decyzji |
|---|---|---|---|
| 1 | Deduplikacja SHA256 przy wgrywaniu | 0,5 dnia | do zrobienia, bez zastrzeżeń |
| 2 | Eksperyment: fine-tuning bge-m3 na żargonie + pomiar | 2–3 dni | warte sprawdzenia |
| 3 | Pomiar próbki pod triaż parsowania | 1 dzień | najpierw pomiar |
| 4 | Generowanie zestawu kontrolnego z dokumentów | 1 dzień | gdy ruszy wielojęzyczność |

Punkt 1 jest niezależny od wszystkiego innego i rozwiązuje istniejący problem. Punkty 2–4
to eksperymenty z jasno określonym sposobem pomiaru — **żadnego z nich nie wdrażać bez
przejścia przez zestaw kontrolny**, zgodnie z zasadą, która w sierpniu dwukrotnie
uchroniła projekt przed pogorszeniem wyników.

---

## Źródła

- [unsloth.ai](https://unsloth.ai/) — strona produktu (Unsloth Desktop)
- [RAG Knowledge Bases — DeepWiki](https://deepwiki.com/unslothai/unsloth/13.3-subprocess-worker-pattern) — architektura potoku RAG
- [Fine-tuning Embedding Models](https://unsloth.ai/docs/basics/embedding-finetuning) — wspierane modele osadzeń
- [PyMuPDF4LLM vs Docling](https://www.file2markdown.ai/blog/pymupdf4llm-vs-docling) — porównanie parserów
- [Unsloth Updates](https://unsloth.ai/docs/new/changelog) — dziennik zmian
