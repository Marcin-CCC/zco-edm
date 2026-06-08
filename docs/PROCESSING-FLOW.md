# Flow Przetwarzania Dokumentów EDM ZCO

**Data:** 2026-06-07  
**Wersja:** 1.0

---

## 1. Przegląd

System EDM (Electronic Document Management) ZCO przetwarza dokumenty przy użyciu trzech głównych komponentów:

- **Next.js Frontend** - interfejs użytkownika
- **FastAPI Backend** - REST API i logika biznesowa
- **n8n + Docling + Qdrant** - pipeline przetwarzania dokumentów

---

## 2. Pełny Flow Po Uploadzie

```mermaid
sequenceDiagram
    participant U as Użytkownik
    participant UI as Next.js Frontend
    participant B as FastAPI Backend
    participant DB as PostgreSQL
    participant N as n8n
    participant D as Docling
    participant Q as Qdrant

    U->>UI: Upload pliku PDF
    UI->>B: POST /api/files/upload
    B->>DB: INSERT files (status=PENDING)
    B->>Dysk: Zapisz plik na dysk
    B->>N: POST N8N_WEBHOOK_URL {file_path, file_id}
    N-->>B: 200 OK
    B->>UI: Zwrot metadanych pliku
    UI->>U: Pokazanie pliku w UI

    N->>D: Parsowanie pliku (Docling OCR)
    D-->>N: Markdown output
    N->>B: PATCH /api/webhook/file/{id}/status {status: "Parsowanie (Docling)"}
    B->>DB: UPDATE files SET status="Parsowanie (Docling)"

    N->>N: Chunkowanie dokumentu
    N->>B: PATCH /api/webhook/file/{id}/status {status: "Chunkowanie"}
    B->>DB: UPDATE files SET status="Chunkowanie"

    N->>Q: Wektoryzacja (Qdrant + Ollama embedding)
    N->>B: PATCH /api/webhook/file/{id}/status {status: "Przetworzono"}
    B->>DB: UPDATE files SET status="Przetworzono"

    U->>UI: Odśwież listę plików
    UI->>B: GET /api/files/?status=Przetworzono
    B->>DB: SELECT files
    DB-->>B: Pliki przetworzone
    B-->>UI: JSON response
    UI->>U: Pokazanie pliku jako "Przetworzono"
```

---

## 3. Statusy Dokumentów

| Status | Opis | Kolor UI |
|--------|------|----------|
| `W kolejce (n8n)` | Plik został załadowany, oczekuje na przetwarzanie przez n8n | Żółty |
| `Parsowanie (Docling)` | n8n parsuje dokument za pomocą Docling (OCR) | Pomarańczowy |
| `Chunkowanie` | Dokument został sparsowany, następuje podział na chunki | Niebieski |
| `Wektoryzacja (Qdrant)` | Chunki są wektoryzowane i zapisywane w Qdrant | Fioletowy |
| `Przetworzono` | Dokument został pomyślnie przetworzony | Zielony |
| `Błąd przetwarzania` | Wystąpił błąd podczas przetwarzania | Czerwony |
| `Pominięto` | Strona/segment został pominięty | Szary |

---

## 4. Endpointy API

### 4.1 Upload Pliku
```
POST /api/files/upload
Content-Type: multipart/form-data

body:
  - file: UploadFile (PDF, DOCX, XLSX, PPTX)
  - folder_id: int (optional)
```
- Tworzy rekord w tabeli `files`
- Zapisuje plik na dysk (`/data/` lub `shared_docs/`)
- Wysyła webhook do n8n (`N8N_WEBHOOK_URL`)
- Zwraca metadane pliku

### 4.2 Lista Plików
```
GET /api/files/?folder_id=&status=&search=&mime_type=&skip=&limit=
```

### 4.3 Aktualizacja Pliku (TYLKO ADMIN)
```
PUT /api/files/{file_id}
Content-Type: application/json

body:
  - status: str (optional)
  - folder_id: int (optional)
  - metadata: JSONB (optional)
```

### 4.4 Pobierz Plik
```
GET /api/files/{file_id}/download
```

### 4.5 Usuń Plik (TYLKO ADMIN)
```
DELETE /api/files/{file_id}
```

### 4.6 Kolejka Przetwarzania
```
GET  /api/processing-queue/?status=&skip=&limit=
GET  /api/processing-queue/{item_id}
POST /api/processing-queue/{item_id}/retry
POST /api/processing-queue/{item_id}/skip-page?page_number=
```

### 4.7 Webhooki (n8n → Backend)
```
PATCH /api/webhook/file/{file_id}/status
Content-Type: application/json

body:
  - status: str (nowy status pliku)
  - ocr_result: str (optional - wynik OCR)
  - metadata: JSONB (optional)
```

---

## 5. Struktura Bazy Danych

### Tabele Kluczowe

#### `files`
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | SERIAL | Klucz główny |
| filename | VARCHAR(500) | Nazwa pliku |
| file_path | VARCHAR(1000) | Ścieżka do pliku na dysku |
| mime_type | VARCHAR(100) | Typ MIME |
| size | BIGINT | Rozmiar w bajtach |
| folder_id | INTEGER | FK do folders |
| uploaded_by | INTEGER | FK do users |
| status | VARCHAR(50) | Status przetwarzania |
| ocr_result | TEXT | Wynik OCR |
| metadata | JSONB | Dodatkowe metadane |
| created_at | TIMESTAMP | Data uploadu |
| updated_at | TIMESTAMP | Data ostatniej aktualizacji |

#### `documents`
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | SERIAL | Klucz główny |
| filename | VARCHAR(255) | Nazwa dokumentu |
| file_path | VARCHAR(500) | Ścieżka do pliku |
| raw_text | TEXT | Sparsowana treść |
| chunks_count | INTEGER | Liczba chunków |
| vector_id | VARCHAR(255) | ID wektora w Qdrant |
| status | VARCHAR(50) | Status |
| metadata | JSONB | Metadane |

#### `processing_queue`
| Kolumna | Typ | Opis |
|---------|-----|------|
| id | SERIAL | Klucz główny |
| document_id | INTEGER | FK do documents |
| status | VARCHAR(50) | Status w kolejce |
| priority | INTEGER | Priorytet |
| started_at | TIMESTAMP | Data rozpoczęcia |
| completed_at | TIMESTAMP | Data zakończenia |
| error_message | TEXT | Komunikat błędu |
| created_at | TIMESTAMP | Data dodania |

---

## 6. Konfiguracja

### Zmienne Środowiskowe (backend/.env)

```bash
# Baza danych
DATABASE_URL=postgresql://postgres:tajne_haslo@postgres_rag_container:5432/edmdatabase

# n8n Webhook
N8N_WEBHOOK_URL=http://192.168.1.34:5678/webhook/document-uploaded

# Przechowywanie plików
STORAGE_DIR=/data
```

---

## 7. Debugowanie

### Logi Backendu
```bash
docker logs edm-backend -f
```

### Sprawdzenie Statusu Pliku w DB
```sql
SELECT id, filename, status, created_at FROM files ORDER BY created_at DESC LIMIT 10;
```

### Sprawdzenie Koleji Przetwarzania
```sql
SELECT pq.id, d.filename, pq.status, pq.error_message 
FROM processing_queue pq 
LEFT JOIN documents d ON pq.document_id = d.id 
ORDER BY pq.created_at DESC LIMIT 10;
```

---

## 8. Potencjalne Problemy

### Problem 1: n8n jest niedostępny
- **Objaw:** Logi backendu pokazują timeout webhooka
- **Rozwiązanie:** N8N_WEBHOOK_URL ma timeout 10s + try/catch. Upload NIE jest blokowany.

### Problem 2: Plik ma status "W kolejce (n8n)" przez długi czas
- **Objaw:** Plik nie jest przetwarzany
- **Rozwiązanie:** Sprawdź czy n8n workflow jest aktywny i trigger webhook działa

### Problem 3: Błąd "Plik nie istnieje na dysku"
- **Objaw:** Download zwraca 404
- **Rozwiązanie:** Sprawdź czy plik istnieje w `/data/` lub `shared_docs/`

---

## 9. Rozwój - Długoterminowe Plany

1. **Migracja do struktury `documents`** - obecnie system używa `files` jako głównej tabeli, ale opisane flow zakłada użycie `documents` + `processing_queue`
2. **Dodanie rate limiting** dla webhooków
3. **Monitorowanie kolejki** - dashboard z metrykami przetwarzania
4. **Retry logic** - automatyczne ponawianie nieudanych operacji

---

## 10. Kontakt

W pytaniach dotyczących flow przetwarzania, kontaktuj się z zespołem developmentowym ZCO.
