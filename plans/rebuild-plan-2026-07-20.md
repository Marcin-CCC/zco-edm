# EDM ZCO — Plan przebudowy

**Data:** 2026-07-20 (aktualizowany 2026-07-22)
**Poprzedni dokument:** [`plans/audit-report-2026-07-05.md`](audit-report-2026-07-05.md) (większość pozycji odrobiona)

---

## STAN NA 2026-07-22 — punkt wznowienia

**Zrobione:** Faza 0 (obserwowalność, sekrety, testy, pinowanie), Faza 1
(atomowość dyspozytora `pg_advisory_lock`), Faza 3.5 (CI/CD natywny build +
runner `spark-zco-edm`), Faza 2.1–2.2 (odporność: przejściowe/trwałe awarie,
callback ERROR w n8n, strażnik pustego rezultatu, whitelist rozszerzeń),
naprawa parsowania **xlsx**.

**Naprawa xlsx (n8n-side, 2026-07-22):** węzeł „Fields mapping" wypuszczał
`cleaned_text`, a „Default Data Loader" czyta `chunk_content`. Fix: Fields
mapping ustawia `chunk_content = {{ $json.markdown_content }}` oraz
`filename = {{ $('Webhook').item.json.body.file_path.split('/').pop() }}`.
Potwierdzone: READY + odpowiedź w czacie ze źródłem.

### Roadmapa klienta (priorytety z rozmowy 2026-07-22)

Kolejność uzgodniona z użytkownikiem:

1. ~~xlsx (bug)~~ ✅ zrobione
2. ~~Fundament: `file_id` w payloadzie Qdranta~~ ✅ zrobione (2026-07-22).
   Dodane JEDNO pole w Default Data Loader: `file_id` =
   `{{ $('Webhook').first().json.body.file_id }}` (bez wiodącego `=`!) —
   pokrywa wszystkie gałęzie (wspólny loader). W Qdrancie `file_id` jako int.
   Kolekcja: `chi_camp_2026`. `folder` odłożony do kroku 6 (RBAC).
   `filename` był już w payloadzie wcześniej (300/300).
3. ~~2.4 — usuwanie wektorów z Qdranta przy delete pliku~~ ✅ zrobione.
   `qdrant_client.delete_vectors_by_file_id` (filtr `metadata.file_id`),
   wpięte w `DELETE /api/files/{id}`, best-effort. Zweryfikowane end-to-end.
4. **Historia rozmów + pamięć czatu (#2 + 3.2)** ← NASTĘPNY KROK. Persistentne rozmowy
   (jak ChatGPT: lista, tytuł = 1. pytanie, wznawianie wątku), backend dokleja
   ostatnie ~5 par Q&A. UWAGA: pamiętać **tylko Q&A, NIE chunki RAG** (to
   powodowało przepełnienie kontekstu). Model odpowiedzi:
   **Qwen/Qwen3-VL-30B-A3B-Instruct** (bge-m3 to embeddingi, nie generacja).
5. **#4** — upload wielu plików naraz (frontend; dyspozytor już obsługuje
   setki PENDING). Na demo bez transferu SSH.
6. **#3 (prawa dostępu)** — foldery-dziedziny, RBAC dla przeglądania I dla
   odpowiedzi czatu (retrieval filtrowany po dozwolonych folderach). Docelowe.

**Odłożone:** 2.0 (dedup wektorów — baza demo i tak będzie czyszczona do zera),
2.5 (krótszy watchdog — ryzykowny, bo są pliki ~40 min; zamiast tego długi
watchdog + callbacki ERROR niosą główny ciężar).

---

## 1. Architektura — stan faktyczny

### Podział zasobów

| Komponent | Lokalizacja | Uwagi |
|-----------|-------------|-------|
| PostgreSQL | Spark, `192.168.1.34:5433` | Dev i prod dzielą **tę samą bazę** |
| Qdrant | Spark, `:6333` | Backend nigdy się z nim nie łączy — używa go wyłącznie n8n |
| n8n | `https://n8n-spark.polmedi.com` | Wystawione publicznie, nie przez IP w LAN |
| Docling | Spark, `:808x` | Wywoływany tylko z n8n; `DOCLING_API_URL` w backendzie jest martwe |
| Ollama / Qwen3VL | Spark | Wywoływane z n8n |
| Pliki | **Spark ORAZ lokalnie** | Dwie kopie — patrz niżej |
| Backend + frontend | Lokalnie (Docker, porty 8001/3002) | Na Sparku działa druga instancja |

### Pliki istnieją w dwóch kopiach

Wbrew założeniu, że pliki żyją tylko na Sparku:

1. `upload_file` zapisuje plik lokalnie do `shared_docs` (montowane jako `/data/shared_docs`),
2. następnie `transfer_to_spark()` wysyła go przez SSH na Sparka,
3. w bazie zapisywana jest **ścieżka sparkowa**,
4. `_resolve_local_path()` odwzorowuje ją z powrotem przy pobieraniu.

**Skutek:** `DELETE /api/files/{id}` kasuje wyłącznie kopię lokalną. Plik na Sparku
zostaje bez żadnego rekordu w bazie — trwały wyciek miejsca i danych.

### Ocena

Podział „ciężkie komponenty na Sparku, aplikacja lokalnie" jest **słuszny**.
Problemem nie jest sam podział, lecz **brak izolacji dev/prod wewnątrz części
sparkowej**. Rozwiązanie: dev dostaje własną bazę, własną kolekcję Qdrant
i własne kopie workflowów — na tym samym sprzęcie.

### Ryzyka wynikające z architektury

| # | Ryzyko | Skutek |
|---|--------|--------|
| A1 | Wspólna baza dev/prod | `Base.metadata.create_all()` przy każdym starcie lokalnego kontenera modyfikuje schemat produkcyjny |
| A2 | Dwa dyspozytory na jednej tabeli | Gwarancja „1 plik naraz" nie obowiązuje; watchdog jednej instancji oznacza ERROR pliki przetwarzane przez drugą |
| A3 | Testy zanieczyszczają produkcję | Uploady testowe trafiają do prod. Qdrant → pojawiają się w odpowiedziach czatu |
| A4 | Klucz SSH = root na Sparku | Mechanizm `ssh → docker exec` daje kontenerowi webowemu pełnię władzy nad maszyną |
| A5 | `BACKEND_CALLBACK_URL` to IP z DHCP | Zmiana IP = callbacki n8n w próżnię = pliki wiszą w PROCESSING, kolejka stoi 30 min |
| A6 | Współdzielone workflowy n8n | Nie da się testować zmian bez ruszania produkcji |

**Do rozstrzygnięcia:** czy `edm-backend` na Sparku działa równolegle z lokalnym.
Musi działać, bo transfer SSH robi na nim `docker exec`. Jeśli tak — A2 jest
aktywnym błędem, nie tylko higieną, i mógł współodpowiadać za pliki w statusie ERROR.

### Konsekwencje dla wdrożenia na Sparka

Wersja produkcyjna musi mieć:
- `SPARK_SSH_TRANSFER=false` (inaczej backend kopiuje pliki sam do siebie),
- własny `BACKEND_CALLBACK_URL`,
- być **jedyną instancją z aktywnym dyspozytorem**.

---

## 2. Kontrakt aplikacja ↔ n8n

Dwa workflowy komunikują się z API i **żaden z tych kontraktów nie jest
wersjonowany ani testowany** — to główne źródło cichych awarii.

### ZCO-EDM-z-Qwen3VL (parsowanie, Published)

```
Webhook → Code → Status PROCESSING sending → Switch on file ext
  ├─ xlsx → Excel parser (pandas) → Fields mapping ─────┐
  ├─ docx ┐                                             │
  └─ pdf  ┴→ Rasterizing → Docling → MD normalization →│
            Text Chunking → router tabel (Qwen3VL) ────┤
                                                        ↓
                                     Merge → Qdrant → Status READY sending
```

**Luki:**
- **Brak callbacku ERROR.** Wysyłane są tylko PROCESSING i READY. Awaria
  w środku = plik wisi w PROCESSING = cała kolejka stoi do watchdoga (30 min).
- **`Switch on file ext` nie pokrywa listy rozszerzeń akceptowanych przez upload.**
  Backend przyjmuje pdf/docx/xlsx/pptx; gałąź docx nie radzi sobie z częścią
  dokumentów, pptx nie ma gałęzi w ogóle. Potwierdzona przyczyna 5 plików w ERROR.

### ZCO - RAG do testowania EDM ZCO (czat)

```
Webhook → Qdrant Vector Store1 → Chunks Filter → AI Agent → Sources Gate → Sources (HTTP)
                ↑ Embeddings Ollama              ↑ OpenAI Chat Model
```

**Luki:**
- ~~Trigger to zwykły Webhook, nie Chat Trigger — streamingu realnie nie ma.~~
  **SKORYGOWANE 2026-07-20:** nod Webhook ma `Respond: Streaming`, czyli
  strumieniuje odpowiedź z węzła wspierającego streaming (AI Agent). Kod
  backendu i frontendu jest napisany zgodnie z tym, co robi workflow.
  Do weryfikacji zostaje, czy **AI Agent ma włączony streaming** — bez tego
  Webhook odda całość jednorazowo mimo ustawienia `Streaming`.
- **Memory niepodpięta** — `sessionId` jest przesyłany, ale nikt go nie konsumuje;
  czat nie pamięta kontekstu, „Nowa rozmowa" nie robi nic.
- **Do weryfikacji:** base URL w credentialach `OpenAI Chat Model`. Jeśli wskazuje
  na prawdziwe API OpenAI, treść dokumentów medycznych opuszcza infrastrukturę —
  przy EDM to problem wywracający priorytety całej listy.

---

## 3. Plan prac

### Faza 0 — Widoczność i bezpieczeństwo ✅ w realizacji

| # | Zadanie | Status |
|---|---------|--------|
| 0.1 | `logging.basicConfig` w `main.py` — bez tego wszystkie `logger.info` aplikacji są wyrzucane (root logger: brak handlerów, poziom WARNING) | ✅ |
| 0.2 | Usunąć zrzut nagłówków (token JWT) i ciała JSON (**hasła z `/api/auth/login`**) z proxy Next.js; bramka `PROXY_DEBUG` | ✅ |
| 0.3 | `print()` → `logger` w `files/router.py` | ✅ |
| 0.4 | Sekret `X-Webhook-Secret` dla `/api/webhook/*` i `/api/chat/sources` (opt-in przez `WEBHOOK_SECRET`) | ✅ |
| 0.5 | Naprawa 7 zepsutych testów (introspekcja `app.routes` → schemat OpenAPI) | ✅ |
| 0.6 | Ustawić `WEBHOOK_SECRET` i dodać nagłówek w nodach HTTP Request w n8n | ✅ dev |
| 0.7 | Ustalić, czy backend jest wystawiony publicznie (n8n jest) | ⬜ ręczne |
| 0.8 | **Przypiąć wersje zależności** (`==` do stanu z 2026-07-21) — świeży build 20/20 | ✅ |
| 0.9 | **Zabezpieczyć triggery webhooków n8n** (kierunek backend → n8n) | ✅ dev |

#### Dwa kierunki komunikacji — nie mylić

```
[1]  backend ──POST──► n8n Webhook (trigger)   : uwierzytelnianie po stronie n8n
[2]  n8n HTTP Request ──PATCH──► backend       : X-Webhook-Secret (zrobione w 0.4)
```

Kierunek [2] jest zabezpieczony. Kierunek [1] **nie jest**: webhooki n8n stoją pod
publiczną domeną `n8n-spark.polmedi.com` bez uwierzytelniania. Kto zna URL, może
odpalić workflow czatu (obciążając GPU Sparka) albo pipeline parsujący. URL-e to
losowe UUID-y, czyli ochrona wyłącznie przez niejawność.

Domknięcie wymaga **obu połówek naraz**: włączenia `Authentication` na nodach
Webhook w n8n ORAZ wysyłania nagłówka przez backend (`N8N_WEBHOOK_AUTH_HEADER` /
`N8N_WEBHOOK_AUTH_VALUE` w `dispatcher.py` i `chat/router.py`). Włączenie samej
strony n8n kończy się `403 Authorization data is wrong!` — zweryfikowane
doświadczalnie 2026-07-20.

#### Znalezisko: niepinowane zależności

`requirements.txt` używa wyłącznie `>=` bez górnej granicy. Build wciągnął
**FastAPI 0.139.2** (przy `fastapi>=0.109.0`), gdzie `include_router` nie
wpłaszcza już tras do `app.routes`, tylko dodaje obiekt `_IncludedRouter`.
Skutek: cała weryfikacja rejestracji endpointów w testach przestała cokolwiek
sprawdzać — 7 testów padało, mimo że aplikacja działa poprawnie.

To zadziałało jak ostrzeżenie, ale następnym razem może pójść w drugą stronę:
**każdy rebuild może wciągnąć wersję, która wywróci działającą aplikację**,
i to na Sparku, nie lokalnie. Do decyzji: przypiąć do wersji dziś działających
(`pip freeze`) czy przyjąć zakresy `~=` z górną granicą.

### Faza 1 — Bezpieczne współistnienie dev/prod (przeskalowana 2026-07-21)

**Decyzja użytkownika:** na etapie demo zostajemy przy JEDNEJ bazie i JEDNYM
n8n (osobna baza pokazywałaby inną listę plików/statusów niż realnie
przetworzone; przenoszenie workflowów między instancjami n8n jest żmudne).
Pełna izolacja dev/prod → dopiero przy wdrożeniu u klienta. To przeskalowuje
Fazę 1: zamiast rozdzielać, czynimy współistnienie na wspólnej bazie bezpiecznym.

| # | Zadanie | Status |
|---|---------|--------|
| 1.1 | Osobna baza dev + Qdrant | ⏸ odłożone (decyzja: jedna baza) |
| 1.2 | Alembic zamiast `create_all()` | ⏸ ryzykowne na żywej wspólnej bazie |
| 1.3 | **Atomowość dyspozytora** — `pg_advisory_xact_lock` w `try_dispatch_next` serializuje wysyłkę między instancjami; oba backendy mogą działać, „1 plik naraz" trzyma się. Zastępuje pomysł `DISPATCHER_ENABLED` (który psułby testy uploadu lokalnie) | ✅ 2026-07-21 |
| 1.4 | Stabilny `BACKEND_CALLBACK_URL` — tylko dev lokalny (IP z DHCP); Spark ma poprawny default. Config env, nie kod | ⬜ opcjonalne |
| 1.5 | Kopie workflowów n8n dla dev | ⏸ odłożone (jedno n8n) |

### Faza 2 — Niezawodność kolejki

| # | Zadanie |
|---|---------|
| 2.0 | **Czyszczenie zdublowanych wektorów w Qdrant** — plik 137 był przetwarzany ~3× podczas debugowania sekretu (n8n kończy przetwarzanie i wypycha wektory ZANIM callback READY wróci; każdy ponowny dispatch = kolejna kopia). Duplikaty zawyżają ranking tych samych treści w czacie. Wiąże się z 2.4 (brak usuwania wektorów) |
| 2.1a | **Odporność backendu na awarie n8n** ✅ 2026-07-21 — dyspozytor rozróżnia awarię PRZEJŚCIOWĄ (n8n nieosiągalny → plik wraca do PENDING, auto-retry) od TRWAŁEJ (n8n zwraca non-200 → ERROR + powód w `metadata.error`). Powód widoczny w kolejce (UI już renderuje `error_message`). Retry/READY czyści stary błąd. Zweryfikowane oboma ścieżkami |
| 2.1b | Callback ERROR w n8n (error workflow na krytycznych nodach → PATCH status ERROR + `metadata.error`) — ⬜ po stronie n8n (instrukcja gotowa). Backend już scala `metadata` z callbacku |
| 2.2 | **Whitelist rozszerzeń w panelu admina** ✅ 2026-07-21 — ustawienie `allowed_extensions` w DB (domyślnie `pdf,docx,xlsx`, zgodne z gałęziami `Switch on file ext`; pptx celowo poza). Upload waliduje po whitelist (odrzuca `.txt` → 400). Edycja w Ustawieniach z normalizacją (lowercase, bez kropek). Zweryfikowane API + odrzucenie uploadu |
| 2.3 | Atomowość dyspozytora — `SELECT ... FOR UPDATE` / advisory lock zamiast `count()` + `commit()` |
| 2.4 | `DELETE` kasuje kopię na Sparku **i** wektory w Qdrant (inaczej usunięty dokument nadal odpowiada w czacie) |
| 2.5 | Konfigurowalny timeout watchdoga (dziś zaszyte 30 min) |

### Faza 3 — Czat

| # | Zadanie |
|---|---------|
| 3.1 | Zweryfikować, czy AI Agent ma włączony streaming (Webhook ma już `Respond: Streaming`) |
| 3.2 | Podpiąć Memory do AI Agent (wykorzystać przesyłany `sessionId`) |
| 3.3 | `file_id` z metadanych Qdrant zamiast dopasowania po nazwie pliku (duplikaty nazw → zły link) |
| 3.4 | Źródła do bazy zamiast `_sources_store` w pamięci procesu |
| 3.5 | Zweryfikować base URL `OpenAI Chat Model` |

### Faza 3.5 — Naprawa CI/CD ✅ (2026-07-21)

Build frontendu w GitHub Actions pada na `RUN npm ci` pod emulacją ARM64:
`qemu: uncaught target signal 4 (Illegal instruction) - core dumped`. Wyszło
po zmianie środowiska runnera przez GitHub (Node 20→24). Job `deploy-spark`
ma `needs: [build-backend, build-frontend]`, więc **każdy przyszły deploy jest
zablokowany** dopóki frontend się nie zbuduje.

Obejście zastosowane 2026-07-21: backend wdrożony ręcznie na Sparku (pull
gotowego obrazu z ghcr.io + `compose up -d backend`), bo jego obraz zbudował
się poprawnie (Python, bez npm). Frontend na Sparku został na starym obrazie.

Rozwiązanie (2026-07-21): trzy joby (build-backend + build-frontend + deploy)
scalone w jeden `build-deploy` budujący natywnie na self-hosted runnerze
Sparka (aarch64) — bez QEMU, bez rundy przez rejestr. Commit `11e31e6`.

**Runner — pułapka infrastruktury.** Job stał w „Waiting for a runner", bo
jedyny runner na Sparku (`~/actions-runner`) został przepięty do repo
`Marcin-CCC/iwound-lab`. Konto `Marcin-CCC` to **user, nie organizacja** →
brak współdzielonych runnerów, każde repo potrzebuje własnego. Rozwiązano
przez drugi runner `~/actions-runner-zco` (nazwa `spark-zco-edm`, label
`zco-edm`), zarejestrowany do zco-edm, obok runnera iwound-lab.

⚠️ **NIETRWAŁE:** runner `spark-zco-edm` działa przez `nohup ./run.sh`
(brak passwordless sudo, więc usługi systemd nie zainstalowano). **Nie
przeżyje reboota Sparka.** Do zrobienia przez użytkownika (sudo):
```
cd ~/actions-runner-zco && sudo ./svc.sh install marcin && sudo ./svc.sh start
```
Stara rejestracja `self-hosted-spark-runner` (offline) — do usunięcia.

### Faza 4 — Porządki

| # | Zadanie |
|---|---------|
| 4.1 | `GET /api/files/categories` i `/folder/{id}/files` przed `/{file_id}` — dziś zwracają 422 |
| 4.2 | `seed.sql`: `DEFAULT 'W kolejce (n8n)'` vs nazwy enumów zapisywane przez ORM |
| 4.3 | `.dockerignore`; `package-lock.json` wyjąć z `.gitignore` (bez niego `npm ci` nie zadziała po świeżym `clone` → blokuje CI/CD); target dev dla frontendu (montowanie `src` do obrazu standalone nie daje hot reloadu) |
| 4.4 | Usunąć martwe `DOCLING_API_URL` i katalog `docling/` |
| 4.5 | Decyzja o tabelach `documents` / `processing_queue` — użyć albo usunąć |
| 4.6 | Aktualizacja `README.md` i `docs/PROCESSING-FLOW.md` (opisują nieistniejący przepływ) |
| 4.7 | Sprzątanie `spark-deploy/` (~30 jednorazowych skryptów) i plików-śmieci z korzenia |
