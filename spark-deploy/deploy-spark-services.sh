#!/bin/bash
# =====================================================
# Deploy PostgreSQL + Docling na Spark DGX
# =====================================================
# Uruchom ten skrypt na Spark DGX:
# chmod +x deploy-spark-services.sh && ./deploy-spark-services.sh

set -e

echo "============================================"
echo " EDM ZCO - Deploy PostgreSQL + Docling"
echo " Spark DGX Deployment Script"
echo "============================================"
echo ""

# Sprawdź czy docker jest dostępny
if ! command -v docker &> /dev/null; then
    echo "BŁĄD: docker nie jest zainstalowany na tym serwerze"
    exit 1
fi

echo "✓ Docker dostępny: $(docker --version)"
echo ""

# Sprawdź czy nvidia-container-toolkit jest zainstalowany
if ! nvidia-smi &> /dev/null; then
    echo "BŁĄD: nvidia-smi nie działa - GPU nie jest dostępne"
    exit 1
fi

echo "✓ NVIDIA GPU dostępne:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1
echo ""

# Utwórz katalogi
DEPLOY_DIR="/opt/edm-zco/spark-services"
mkdir -p "$DEPLOY_DIR"

echo "📦 Kopiowanie plików do $DEPLOY_DIR..."

# Skopiuj pliki konfiguracyjne
cp "$(dirname "$0")/docker-compose-spark-services.yaml" "$DEPLOY_DIR/"

# Skopiuj Docling (jeśli skrypt jest uruchamiany lokalnie)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -d "$PROJECT_ROOT/docling" ]; then
    echo "Building Docling image from $(realpath "$PROJECT_ROOT/docling")..."
    cd "$PROJECT_ROOT/docling"
    
    echo "🔨 Budowanie obrazu Docling..."
    docker build -t edm-docling-spark:latest .
    
    echo "✓ Obraz Docling zbudowany: $(docker images edm-docling-spark:latest --format '{{.ID}} {{.Size}}')"
else
    echo "⚠️  Katalog docling nie znaleziony - upewnij się że obraz edm-docling-spark:latest istnieje"
fi

echo ""
echo "🐳 Uruchamianie usług..."
cd "$DEPLOY_DIR"
docker compose up -d

echo ""
echo "⏳ Czekanie na start usług..."
sleep 15

echo ""
echo "=== Status kontenerów ==="
docker compose ps

echo ""
echo "=== Sprawdź health check PostgreSQL ==="
docker exec edm-postgres-spark pg_isready -U postgres

echo ""
echo "=== Sprawdź Docling API ==="
sleep 45
curl -s http://localhost:8002/docs > /dev/null 2>&1 && echo "✓ Docling API dostępny na :8002" || echo "⏳ Docling wciąż się ładuje (modele AI)... spróbuj za 2 minuty"

echo ""
echo "============================================"
echo " Deploy completed!"
echo "============================================"
echo ""
echo "PostgreSQL:  postgresql://postgres:tajne_haslo@localhost:5432/edmdatabase"
echo "Docling API: http://localhost:8002"
echo "Docling docs: http://localhost:8002/docs"
echo ""
echo "Logi:"
echo "  docker compose logs -f postgres"
echo "  docker compose logs -f docling-api"
echo ""
echo "Aby zatrzymać usługi:"
echo "  docker compose down"
echo ""