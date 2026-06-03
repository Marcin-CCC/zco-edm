# EDM ZCO - System Zarzadzania Dokumentami

System do zarządzania dokumentami medycznymi, stworzony do dzialania na infrastruktury DGX Spark.

## Struktura projektu

```
zco-edm-final/
├── backend/              # FastAPI backend
│   ├── app/              # Kod aplikacji
│   ├── tests/            # Testy pytest
│   ├── Dockerfile        # Image Docker dla backendu
│   ├── requirements.txt  # ZaleZNOSCI Python
│   ├── seed.sql        # Inicjalizacja bazy danych
│   └── .env.example    # Template zmiennych srodowiskowych
├── frontend/             # Next.js frontend
│   ├── src/              # Kod aplikacji
│   ├── Dockerfile        # Image Docker dla frontendu
│   ├── package.json      # ZaleZNOSCI Node.js
│   └── tailwind.config.js # Tailwind CSS konfig
├── spark-deploy/         # Skrypty do wdrozenia na Spark
├── docker-compose.yaml   # Glówna konfig Docker Compose
├── docker-compose.dev.yaml # Konfig dla developemntu lokalnego
└── .github/workflows/    # CI/CD GitHub Actions
```

## Wymagania

- Docker i Docker Compose (v2+)
- Git
- SSH dostep do Spark (192.168.1.34)

## Instalacja lokalna (dev)

```bash
# Skopiuj plik .env.example do .env i edytuj wartości
cp .env.example .env

# Uruchom lokalnie (dev mode, wylaczyc postgres)
docker compose --profile dev up -d

# Albo wylaczony (bez postgres - jezeli masz wlasna baz)
docker compose up -d
```

Usługi dostepne pod:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8083
- **API Docs:** http://localhost:8083/docs

## Wdrozenie na Spark DGX

### Opcja 1: CI/CD przez GitHub Actions (ZALECANA)

1. **Konfiguracja repozytorium GitHub:**
   - Wgraj kod na GitHub
   - Dodaj secret `SPARK_SSH_PRIVATE_KEY` w Settings → Secrets → Actions
   - Secret powinien zawierac klucz SSH prywatny do logowania na Spark

2. **Workflow GitHub Actions:**
   - Push na `main` lub `spark` triggeruje wdrozenie
   - Automatyczne testy → budowanie image'ów → deploy
   - Image pushowane do GitHub Container Registry (ghcr.io)

3. **Reczowne wdrozenie (workflow_dispatch):**
   ```
   GitHub → Actions → "Deploy to Spark" → Run Workflow
   ```

### Opcja 2: Reczowne wdrozenie (SSH)

```bash
# Wgraj kod na Spark
scp -r backend/ frontend/ docker-compose.yaml .env.example marcin@192.168.1.34:/home/marcin/zco-edm-app/

# Loguj do Spark
ssh marcin@192.168.1.34

# Na Spark:
cd /home/marcin/zco-edm-app
cp .env.example .env
# Edytuj .env - zmien NEXT_PUBLIC_API_URL na http://172.17.0.1:8083

# Wdroz
docker compose --profile spark up --build -d
```

### Opcja 3: Docker Compose (bez GitHub)

```bash
# Na Spark:
cd /home/marcin/zco-edm-app

# Upewnij sie ze .env istnieje
cat .env

# Wdroz
docker compose --profile spark up -d
```

## Konfiguracja

### Zmienne srodowiskowe (.env)

```bash
# PORTY
FRONTEND_PORT=3000
BACKEND_PORT=8083

# URL dla frontendu - KLUCZOWE dla Docker na Spark
NEXT_PUBLIC_API_URL=http://172.17.0.1:8083

# Baza danych
DATABASE_URL=postgresql+psycopg2://postgres:tajne_haslo@edm-zco-postgres:5432/edmdatabase

# Bezpieczenstwo
SECRET_KEY=zmien-to-na-randomowy-ciag-znakow

# Usugi zewnetrzne
QDRANT_URL=http://192.168.1.34:6333
N8N_WEBHOOK_URL=http://192.168.1.34:5678/webhook/document-uploaded
DOCLING_API_URL=http://docling:8002
OLLAMA_API_URL=http://192.168.1.34:11434

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

### Kluczowa roznica: NEXT_PUBLIC_API_URL

| Środowisko          | NEXT_PUBLIC_API_URL            |
|---------------------|--------------------------------|
| Docker internal     | http://backend:8000            |
| Spark host access   | http://172.17.0.1:8083         |
| Local dev           | http://localhost:8083          |

**Na Spark:** Frontend dziala w osobnym kontenerze, ale dostep z hosta odbywa sie przez `172.17.0.1:8083`. Stąd URL musi byc ustawiony na `http://172.17.0.1:8083`.

## Testy

### Backend
```bash
cd backend
pip install pytest
pytest tests/ -v
```

### Linting
```bash
cd backend
pip install flake8
flake8 app/ --count --max-complexity=10 --max-line-length=127 --statistics
```

## Rozwiazywanie problemow

### Frontend nie laduje
1. Sprawdz logi: `docker logs edm-frontend`
2. Sprawdz czy NEXT_PUBLIC_API_URL jest poprawny
3. Sprawdz czy backend jest dostepny: `curl http://localhost:8083/api/health`

### Backend nie dziala
1. Sprawdz logi: `docker logs edm-backend`
2. Sprawdz połączenie z baza: `docker exec edm-backend curl -sf http://localhost:8000/api/health`
3. Upewnij sie ze postgres dziala

### Błąd bcrypt (hasla nie dzialaja)
- Upewnij sie ze hasla w bazie sa poprawnie zaszyfrowane
- Sprawdź czy jwt_handler.py uzywa `bcrypt.checkpw` z truncacja 72-bajtowa
- Nowe hasla powinny byc generowane przez `/api/auth/register`

### Port juz zajety
```bash
# Sprawdz co dziala na porcie
sudo lsof -i :3000
sudo lsof -i :8083

# Zatrzymaj stare kontenery
docker stop edm-frontend-spark
docker rm edm-frontend-spark
```

## Struktura bazy danych

Tabele tworzone automatycznie przez `Base.metadata.create_all()` w `app/main.py`:
- `users` - uzytkownicy systemu
- `folders` - foldery dla dokumentow
- `documents` - dokumenty/ pliki
- `document_versions` - wersje dokumentow
- `access_packages` - pakiety dostepow
- `user_access` - dostepy uzytkownikow
- `user_passwords` - hasla uzytkownikow

## Architektura

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Frontend   │────▶│   Backend    │────▶│   PostgreSQL  │
│  Next.js    │     │  FastAPI     │     │   Database    │
│  :3000      │     │  :8000       │     │               │
└─────────────┘     └──────────────┘     └──────────────┘
                          │
                ┌─────────┼──────────┐
                │         │          │
                ▼         ▼          ▼
           ┌────────┐ ┌──────┐ ┌────────┐
           │ Qdrant │ │ n8n  │ │Ollama  │
           └────────┘ └──────┘ └────────┘
```

## Wersje

- **Backend API:** FastAPI + Python 3.11
- **Frontend:** Next.js 16 + Node.js 20
- **Database:** PostgreSQL 15
- **Vector DB:** Qdrant

## Autorzy

ZCO EDM Team