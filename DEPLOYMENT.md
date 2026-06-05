# 🚀 Deployment Guide — ZCO EDM on Spark DGX

## Spis treści

1. [Architektura](#architektura)
2. [Self-Hosted Runner](#self-hosted-runner)
3. [GitHub Actions Workflow](#github-actions-workflow)
4. [Procedura deploy](#procedura-deploy)
5. [Proces zmian i deploy](#proces-zmiann-i-deploy)
6. [Weryfikacja wdrożenia](#weryfikacja-wdrożenia)
7. [Rollback](#rollback)
8. [Troubleshooting](#troubleshooting)

---

## Architektura

```
┌─────────────────────────┐
│   GitHub (Repository)   │
│   Marcin-CCC/zco-edm    │
└────────┬────────────────┘
         │ push do master/main/spark
         ▼
┌─────────────────────────┐
│   GitHub Actions        │
│   ├─ test-backend       │
│   ├─ build-backend      │
│   └─ build-frontend     │
└────────┬────────────────┘
         │ push obrazów do GHCR
         ▼
┌─────────────────────────┐
│   GHCR (Registry)       │
│   ghcr.io/marcin-ccc/   │
│   zco-edm/backend:*     │
│   zco-edm/frontend:*    │
└────────┬────────────────┘
         │ docker pull
         ▼
┌─────────────────────────┐
│   Spark DGX             │
│   192.168.1.34          │
│   ┌──────────────────┐  │
│   │ self-hosted      │  │
│   │ runner           │  │
│   │ (actions.runner) │  │
│   └────────┬─────────┘  │
│            │ docker     │
│            │ compose    │
│            │ pull + up  │
│            ▼            │
│   ┌──────────────────┐  │
│   │ edm-backend      │  │
│   │ edm-frontend     │  │
│   │ (kontenery)      │  │
│   └──────────────────┘  │
└─────────────────────────┘
```

---

## Self-Hosted Runner

### Lokalizacja
- **Host:** `spark-d039` (192.168.1.34)
- **User:** `marcin`
- **Ścieżka:** `/home/marcin/actions-runner/`
- **Service:** `actions.runner.Marcin-CCC-zco-edm.self-hosted-spark-runner.service`

### Instalacja (wykonano)
```bash
# Na spark-d039
cd /home/marcin

# Klon repozytorium
git clone https://github.com/Marcin-CCC/zco-edm.git
cd zco-edm

# Instalacja runnera
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.32.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.32.0/actions-runner-linux-x64-2.32.0.tar.gz
tar zxvf actions-runner-linux-x64-2.32.0.tar.gz

# Konfiguracja
./config.sh --url https://github.com/Marcin-CCC/zco-edm --token <PAT>
./svcinstall.sh

# Uruchomienie service
sudo systemctl start actions.runner.Marcin-CCC-zco-edm.self-hosted-spark-runner.service
sudo systemctl enable actions.runner.Marcin-CCC-zco-edm.self-hosted-spark-runner.service
```

### Status
- **Runner name:** `self-hosted-spark-runner`
- **Labels:** `linux`, `x64`, `ubuntu`
- **Status:** active, connected, listening for jobs

---

## GitHub Actions Workflow

### Plik
`.github/workflows/deploy-spark.yml`

### Wykonywanie (trigger)
- **Push** do branchy: `master`, `main`, `spark`
- **Manual trigger:** `workflow_dispatch`
- **PR** do `main` (tylko build + test, bez deploy)

### Job'y
| Job | Runs On | Opis |
|-----|---------|------|
| `test-backend` | `ubuntu-latest` | Testy + lint Python |
| `build-backend` | `ubuntu-latest` | Budowanie obrazu backendu z SHA tagiem |
| `build-frontend` | `ubuntu-latest` | Budowanie obrazu frontendu z SHA tagiem |
| `deploy-spark` | `self-hosted` | Deploy na Spark DGX |

### Tagi obrazów
- **SHA:** `ghcr.io/marcin-ccc/zco-edm/backend:backend-<sha>`
- **SHA:** `ghcr.io/marcin-ccc/zco-edm/frontend:frontend-<sha>`
- **Latest:** `ghcr.io/marcin-ccc/zco-edm/backend:latest`
- **Latest:** `ghcr.io/marcin-ccc/zco-edm/frontend:latest`

---

## Procedura deploy

### Automatycznie (przez GitHub Actions)

1. **Zrób commit na master:**
   ```bash
   git add .
   git commit -m "your change description"
   git push origin master
   ```

2. **GitHub Actions automatycznie:**
   - Uruchamia testy backendu
   - Buduje i push'uje obrazy do GHCR z SHA tagiem
   - Po pomyślnym build → deploy na Spark

3. **Workflow logi:**
   ```bash
   gh run list --limit 3
   gh run view <ID> --log-failed
   ```

### Ręcznie (na Spark DGX)

Jeśli chcesz ręcznie trigger-ować deployment:

```bash
# Na spark-d039
cd /home/marcin/zco-edm-app

# Tworzenie .env z aktualnym SHA
cat > .env << EOF
BUILD_TAG_BACKEND=ghcr.io/marcin-ccc/zco-edm/backend:backend-<SHA_COMMITU>
BUILD_TAG_FRONTEND=ghcr.io/marcin-ccc/zco-edm/frontend:frontend-<SHA_COMMITU>
EOF

# Pobranie nowych obrazów i restart
docker compose --profile spark pull
docker compose --profile spark up -d

# Weryfikacja
docker ps
curl http://localhost:8083/api/health
```

### Krok po kroku (deploy step)

Workflow deploy step wykonuje:

```bash
cd /home/marcin/zco-edm-app

# 1. Checkout kodu (już zrobione przez runner)
# Runner checkout-uje repo

# 2. Tworzenie .env z SHA tagami
cat > .env << EOF
BUILD_TAG_BACKEND=ghcr.io/marcin-ccc/zco-edm/backend:backend-<SHA>
BUILD_TAG_FRONTEND=ghcr.io/marcin-ccc/zco-edm/frontend:frontend-<SHA>
EOF

# 3. Pull obrazów z GHCR
docker compose --profile spark pull

# 4. Restart kontenerów z nowymi obrazami
docker compose --profile spark up -d

# 5. Weryfikacja
curl -sf --max-time 10 http://localhost:8083/api/health
curl -sf --max-time 10 http://localhost:8083/api/health/info
curl -sf --max-time 5 http://localhost:3000 > /dev/null
```

---

## Proces zmian i deploy

### Proces pracy (krok po kroku)

| Krok | Akcja | Gdzie | Głos ownership |
|------|-------|-------|----------------|
| **1** | Poprawki w kodzie | Local repo | AI (Cline) |
| **2** | Budowanie i testy lokalne | `docker-compose.dev.yaml` | AI (Cline) |
| **3** | Commit + push do GitHub | Local git | AI (Cline) |
| **4** | Czekam na polecenie deploy | — | User (decyzja) |
| **5** | Deploy na Spark | SSH + docker compose | AI (Cline) |
| **6** | Testy na Sparku | SSH + curl | User |
| **7** | Rollback (jeśli potrzebny) | SSH + docker compose | AI (Cline) |

### Krok 1: Poprawki w kodzie (AI)
- AI nanosi zmiany w lokalnym repozytorium
- Zmiany obejmują frontend (`frontend/`) i backend (`backend/`)

### Krok 2: Testy lokalne (AI)
- Uruchomienie dev environment przez `docker-compose.dev.yaml`:
  ```bash
  $env:COMPOSE_PROJECT_NAME="edm-dev"; docker compose -p edm-dev -f docker-compose.dev.yaml up -d --build
  ```
- **Backend:** `http://localhost:8001` (łączy się do PG na Spark: 192.168.1.34:5433)
- **Frontend:** `http://localhost:3002` (API call do localhost:8001)

### Krok 3: Commit + push (AI)
- Po sukcesie testów lokalnych:
  ```bash
  git add .
  git commit -m "feat: opis zmian - v<version>"
  git push origin master
  ```
- GitHub Actions automatycznie buduje obrazy i push'uje do GHCR

### Krok 4: Czekam na polecenie (User)
- AI informuje użytkownika że testy lokalne zakończyły się sukcesem
- Użytkownik decyduje kiedy deploy na Spark

### Krok 5: Deploy na Spark (AI + User decyzja)

#### Decyzja: `pull` vs `build`

| Zmiana | Rekomendacja | Dlaczego |
|--------|--------------|----------|
| Tylko kod aplikacji (.py, .tsx, .css, itp.) | **pull** | GitHub Actions już zsbuildowało obrazy |
| Zmiana w Dockerfile | **build** | Dockerfile wymaga ponownej kompilacji |
| Zmiana w requirements.txt / package.json | **pull** | GitHub Actions obsługuje w build |
| Zmiana w docker-compose.yaml | **build** | Struktura kontenerów się zmieniła |
| Zmiana w .env / config secrets | **pull** + restart | Obraz ten sam, zmiana env |

#### Pull (szybsze, preferowane):
```bash
ssh marcin@192.168.1.34 "cd /home/marcin/zco-edm-app && docker compose --profile spark pull && docker compose --profile spark up -d"
```

#### Build (gdy Dockerfile/docker-compose się zmienił):
```bash
ssh marcin@192.168.1.34 "cd /home/marcin/zco-edm-app && docker compose --profile spark up -d --build"
```

### Krok 6: Testy na Spark (User)
- Użytkownik wykonuje testy na wdrożonym Spark:
  ```bash
  # Weryfikacja kontenerów
  docker ps --format "table {{.Names}}\t{{.Status}}"
  
  # Weryfikacja API
  curl http://localhost:8083/api/health
  curl http://localhost:8083/api/health/info
  
  # Testy UI w przeglądarce
  http://192.168.1.34:3000
  ```

### Krok 7: Rollback (jeśli testy spadają)
```bash
ssh marcin@192.168.1.34 "cd /home/marcin/zco-edm-app && docker compose --profile spark down && docker compose --profile spark up -d"
```

### Versioning
- Po każdym wdrożeniu sprawdzam wersję:
  ```bash
  curl http://localhost:8083/api/version
  ```
- Wersja notowana w commit message

---

## Weryfikacja wdrożenia

### SSH na Spark
```bash
ssh marcin@192.168.1.34
```

### Sprawdź kontenery
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```
- Nowe kontenery powinny mieć `Up X minutes` (po deploymentzie)
- Przed: `Up X hours/days`

### Sprawdź obrazy
```bash
docker image ls | grep zco-edm
```
Powinno pokazać:
```
ghcr.io/marcin-ccc/zco-edm/backend   backend-<sha>
ghcr.io/marcin-ccc/zco-edm/frontend  frontend-<sha>
```

### Endpointy
```bash
# Backend health
curl http://localhost:8083/api/health
# Expected: {"status":"ok","database":"connected"}

# Backend health/info (nowy endpoint!)
curl http://localhost:8083/api/health/info
# Expected: detailed info

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Expected: 200
```

### Logi
```bash
docker logs --tail 50 edm-backend
docker logs --tail 50 edm-frontend
```

---

## Rollback

### Szybki rollback (przełączenie na poprzedni obraz)
```bash
# Na Spark — restart z poprzednim obrazem
docker compose --profile spark -f docker-compose.yaml up -d

# Lub ręcznie z określeniem starego tagu
cat > .env << EOF
BUILD_TAG_BACKEND=ghcr.io/marcin-ccc/zco-edm/backend:backend-<STARY_SHA>
BUILD_TAG_FRONTEND=ghcr.io/marcin-ccc/zco-edm/frontend:frontend-<STARY_SHA>
EOF

docker compose --profile spark pull up -d
```

### Rollback przez GitHub
```bash
# Ręczny trigger workflow z poprzedniego commitu
cd zco-edm
git checkout <stary-commit>
git push origin master  # tymczasowo
# Poczekaj na workflow completion
git checkout master
```

---

## Troubleshooting

### Problem: Runner nie słucha job'ów
```bash
# Na spark-d039
sudo systemctl status actions.runner.Marcin-CCC-zco-edm.self-hosted-spark-runner.service
sudo systemctl restart actions.runner.Marcin-CCC-zco-edm.self-hosted-spark-runner.service

# Sprawdź logs
tail -f /home/marcin/actions-runner/_diag/Runner_20260604.log
```

### Problem: Workflow error — `docker compose pull up -d`
Przyczyna: `pull` i `up` to są dwa różne podpolecenia docker compose.
**Rozwiązanie:** Rozdziel na dwie linie:
```bash
docker compose --profile spark pull
docker compose --profile spark up -d
```

### Problem: Kontener nie restartuje się po deploy
```bash
# Sprawdź czy obraz został pobrany
docker image ls | grep zco-edm

# Sprawdź czy .env ma poprawne tagi
cat /home/marcin/zco-edm-app/.env

# Restart ręczny
cd /home/marcin/zco-edm-app
docker compose --profile spark down
docker compose --profile spark up -d
```

### Problem: `{"detail":"Not Found"}` na `/api/health/info`
Przyczyna: Container running an older version without the new endpoint.
**Rozwiązanie:** Trigger-uj deployment ponownie (patrz wyżej).

### Problem: Obrazy nie są pull-owane
Przyczyna: docker compose nie ładuje .env z właściwymi tagami.
**Rozwiązanie:** Upewnij się że `.env` istnieje i zawiera:
```
BUILD_TAG_BACKEND=ghcr.io/marcin-ccc/zco-edm/backend:backend-<sha>
BUILD_TAG_FRONTEND=ghcr.io/marcin-ccc/zco-edm/frontend:frontend-<sha>
```

---

## Ścieżki na Spark

```
/home/marcin/
├── actions-runner/                  # Self-hosted runner
│   ├── config.sh
│   ├── _diag/                       # Logs runnera
│   └── _work/zco-edm/               # Workspace runnera
├── zco-edm/                         # Klon repozytorium
│   └── .github/workflows/deploy-spark.yml
└── zco-edm-app/                     # Katalog docker compose
    ├── docker-compose.yaml          # Definicja services
    ├── .env                         # SHA tagi (tworzone przez workflow)
    └── shared_docs/                 # Volumeny
```

## Env vars w docker-compose.yaml

| Zmienna | Domyślna wartość | Opis |
|---------|------------------|------|
| `BUILD_TAG_BACKEND` | `ghcr.io/marcin-ccc/zco-edm/backend:latest` | Tag obrazu backendu |
| `BUILD_TAG_FRONTEND` | `ghcr.io/marcin-ccc/zco-edm/frontend:latest` | Tag obrazu frontendu |
| `BACKEND_PORT` | `8083` | Port backendu |
| `FRONTEND_PORT` | `3000` | Port frontendu |
| `NEXT_PUBLIC_API_URL` | `http://backend:8000` | URL API dla frontendu |
| `DATABASE_URL` | `postgresql+psycopg2://postgres:tajne_haslo@edm-zco-postgres:5432/edmdatabase` | URL bazy danych |
| `QDRANT_URL` | `http://192.168.1.34:6333` | URL Qdrant vector DB |
| `N8N_WEBHOOK_URL` | `http://192.168.1.34:5678/webhook/document-uploaded` | URL n8n webhook |
| `DOCLING_API_URL` | `http://docling:8002` | URL docling API |
| `OLLAMA_API_URL` | `http://192.168.1.34:11434` | URL Ollama |