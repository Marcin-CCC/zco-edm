# Plan: Ustawienia aplikacji - Webhook URL

## Cel
Umożliwić administratorowi zmianę adresu webhooka do przetwarzania plików przez panel UI zamiast zmiennych środowiskowych.

## Stan obecny
- `N8N_WEBHOOK_URL` jest statyczną zmienną w [`backend/app/config.py:36`](backend/app/config.py:36)
- URL jest używany w [`backend/app/files/router.py:129`](backend/app/files/router.py:129) podczas uploadu pliku
- Brak tabeli settings w bazie danych
- Sidebar ma 3 podpozycje w Administracji: Użytkownicy, Pakiety praw, Kolejka plików

## Rozwiązanie

### 1. Backend - Tabela ustawień (Settings)

**Nowa tabela w bazie danych (`settings`):**

| Kolumna | Typ | Opis |
|---------|-----|------|
| id | INTEGER PK | ID ustawienia |
| key | VARCHAR(100) UNIQUE | Klucz (np. `n8n_webhook_url`) |
| value | TEXT | Wartość |
| updated_at | TIMESTAMP | Data modyfikacji |

**Migracja:** Dodać migration SQL w [`backend/seed.sql`](backend/seed.sql):
```sql
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Wstępna wartość webhooka
INSERT INTO settings (key, value) VALUES ('n8n_webhook_url', 'http://192.168.1.34:5678/webhook/document-uploaded')
ON CONFLICT (key) DO NOTHING;
```

**Nowy model:** [`backend/app/models.py`](backend/app/models.py) - klasa `Settings`

**Router:** Nowy plik [`backend/app/settings/router.py`](backend/app/settings/router.py):
- `GET /api/settings` - pobierz wszystkie ustawienia jako JSON key-value
- `PUT /api/settings/n8n_webhook_url` - zaktualizuj webhook URL

### 2. Backend - Integracja z uploadem

Zmiana w [`backend/app/files/router.py`](backend/app/files/router.py):
- Odczyt webhook URL z bazy danych (z fallbackiem do `settings.N8N_WEBHOOK_URL` z env)
- Cache w pamięci z odświeżaniem po każdej aktualizacji

### 3. Frontend - Nowa strona Ustawienia

**Router:** [`frontend/src/app/dashboard/settings/page.tsx`](frontend/src/app/dashboard/settings/page.tsx)

**UI:**
- Tytuł: "Ustawienia aplikacji"
- Pole tekstowe: "Adres webhooka do przetwarzania pliku"
- Przycisk "Zapisz"
- Walidacja URL (format: http/https + host + path)
- Komunikaty sukcesu/błędu

### 4. Frontend - Sidebar i nawigacja

Dodanie do [`frontend/src/components/sidebar.tsx`](frontend/src/components/sidebar.tsx:23):
```
{ label: 'Ustawienia', href: '/dashboard/settings', roles: ['admin'], children: ['/dashboard/settings'] }
```

Dodanie do [`frontend/src/app/dashboard/layout.tsx`](frontend/src/app/dashboard/layout.tsx:15-18):
- Dodaj `{ label: 'Ustawienia aplikacji', href: '/dashboard/settings' }` do `ADMIN_SUBMENU`
- Dodaj `/dashboard/settings` do `PAGES_WITH_TABS`

### 5. Frontend - API client

Dodanie do [`frontend/src/lib/api.ts`](frontend/src/lib/api.ts):
```typescript
export const settingsApi = {
  get: () =>
    apiRequest<any>('/api/settings', { method: 'GET', token: getAuthToken() }),
  updateWebhook: (url: string) =>
    apiRequest<any>('/api/settings/n8n_webhook_url', {
      method: 'PUT',
      body: { url },
      token: getAuthToken(),
    }),
};
```

### 6. Backend - Rejestracja routera

Dodanie do [`backend/app/main.py`](backend/app/main.py):
```python
from app.settings.router import router as settings_router
app.include_router(settings_router)
```

## Struktura plików

```
backend/
  app/
    settings/
      __init__.py
      router.py
    models.py          (+ Settings model)
    schemas.py          (+ Settings schemas)
    main.py             (+ settings_router)
  seed.sql              (+ settings table)

frontend/
  src/
    app/
      dashboard/
        settings/
          page.tsx      (+ nowa strona)
    components/
      sidebar.tsx       (+ Ustawienia w menu)
    lib/
      api.ts            (+ settingsApi)
```

## Kolejność implementacji

1. Backend: Tabela settings + model + migracja seed.sql
2. Backend: Router settings (GET/PUT)
3. Backend: Rejestracja routera + main.py
4. Backend: Integracja z uploadem (files/router.py)
5. Frontend: API client (settingsApi)
6. Frontend: Sidebar + layout (nawigacja)
7. Frontend: Strona settings (UI)
8. Budowanie i restart kontenerów

## Diagram architektury

```mermaid
flowchart TB
    subgraph Frontend
        UI[UI Ustawienia] --> API[settingsApi]
    end
    
    subgraph NextJS Proxy
        Proxy[/api/settings/*]
    end
    
    subgraph Backend FastAPI
        Router[settings/router.py]
        Router --> DB[(settings table)]
        Router --> Cache[Cache w pamięci]
        Cache --> Upload[files/router.py]
    end
    
    UI --> Proxy
    Proxy --> Router
```

## Uwagi
- Webhook URL będzie dynamiczny - bez potrzeby restartu serwisu
- Fallback do zmiennych środowiskowych w przypadku braku w DB
- Nowe ustawzenia mogą być rozszerzane w przyszłości (DOCLING_URL, OLLAMA_URL itp.)
