#!/bin/bash
# =====================================================
# EDM ZCO - Deploy to Spark DGX
# =====================================================
# Skrypt kopiujcy lokalne zmiany na Spark
# Użycie: bash spark-deploy/deploy.sh [backend|frontend|all]
# =====================================================
#
# Uwagi:
# - Skrypt używa `docker compose -f docker-compose.yaml` (jawnie okrešlony plik)
#   aby uniknąć pomyłki z innymi plikami compose (np. docker-compose.dev.yaml).
# - Port backendu ujednolicony do 8083 (zgodnie z docker-compose.yaml: BACKEND_PORT:-8083).
# - BACKEND_URL w build-arg frontendu: http://172.17.0.1:8083
#   172.17.0.1 = Docker gateway (adres hosta z kontenera frontendu)
#   8083 = port backendu dostepny z zewnatrz kontenera (mapowanie :8000 -> :8083)
#   Next.js wymaga BACKEND_URL w czasie buildu (compile-time env vars).
#   Na Sparku upewnij sie, że plik .env zawiera BACKEND_PORT=8083.
# =====================================================

set -e

SPARK_DIR="/home/marcin/zco-edm-app"
SPARK_IP="spark"  # alias SSH w ~/.ssh/config

MODE="${1:-all}"

echo "============================================"
echo "  EDM ZCO - Deploy to Spark"
echo "  Mode: $MODE"
echo "  Target: $SPARK_IP:$SPARK_DIR"
echo "============================================"

# --- Deploy Backend ---
deploy_backend() {
    echo ""
    echo "--- Deploying Backend ---"

    # Kopiuj Dockerfile (z opcja --reload dla developmet)
    echo "  Kopiowanie Dockerfile..."
    scp backend/Dockerfile "${SPARK_IP}:${SPARK_DIR}/backend/Dockerfile"

    # Kopiuj requirements.txt
    echo "  Kopiowanie requirements.txt..."
    scp backend/requirements.txt "${SPARK_IP}:${SPARK_DIR}/backend/requirements.txt"

    # Kopiuj cala strukture modułów backendu (w tym settings, processing_queue, webhooks, itp.)
    echo "  Kopiowanie kodu backend..."
    scp -r backend/app/* "${SPARK_IP}:${SPARK_DIR}/backend/app/"

    # Kopiuj seed.sql (jeśli są zmiany schematu bazy danych)
    echo "  Kopiowanie seed.sql..."
    scp backend/seed.sql "${SPARK_IP}:${SPARK_DIR}/backend/seed.sql"

    # Kopiuj pliki konfiguracyjne
    scp backend/.env.spark "${SPARK_IP}:${SPARK_DIR}/backend/.env.spark"

    # Rebuild i restart (jawnie okrešl docker-compose.yaml)
    echo "  Budowanie i restart backend..."
    ssh "${SPARK_IP}" "cd ${SPARK_DIR} && docker compose -f docker-compose.yaml --profile spark up -d --build backend"

    echo "  Backend zdeployony."
}

# --- Deploy Frontend ---
deploy_frontend() {
    echo ""
    echo "--- Deploying Frontend ---"

    # Kopiuj Dockerfile
    echo "  Kopiowanie Dockerfile..."
    scp frontend/Dockerfile "${SPARK_IP}:${SPARK_DIR}/frontend/Dockerfile"

    # Kopiuj package.json
    echo "  Kopiowanie package.json..."
    scp frontend/package.json "${SPARK_IP}:${SPARK_DIR}/frontend/package.json"

    # Kopiuj next.config.js
    echo "  Kopiowanie next.config.js..."
    scp frontend/next.config.js "${SPARK_IP}:${SPARK_DIR}/frontend/next.config.js"

    # Kopiuj tsconfig.json
    echo "  Kopiowanie tsconfig.json..."
    scp frontend/tsconfig.json "${SPARK_IP}:${SPARK_DIR}/frontend/tsconfig.json"

    # Kopiuj caly src frontendu
    echo "  Kopiowanie src..."
    scp -r frontend/src/* "${SPARK_IP}:${SPARK_DIR}/frontend/src/"

    # Kopiuj .env.dev (dla pewnosci, ze Spark ma correct API URL)
    scp frontend/.env.dev "${SPARK_IP}:${SPARK_DIR}/frontend/.env.dev"

    # Rebuild i restart (BACKEND_URL musi byc ustawiony dla Spark)
    # BACKEND_URL=http://172.17.0.1:8083:
    #   172.17.0.1 = Docker gateway (host fizyczny dostepny z kontenera)
    #   8083 = port backendu na hošcie (zgodnie z docker-compose.yaml BACKEND_PORT:-8083)
    echo "  Budowanie i restart frontend..."
    ssh "${SPARK_IP}" "cd ${SPARK_DIR} && docker compose -f docker-compose.yaml --profile spark up -d --build --build-arg BACKEND_URL=http://172.17.0.1:8083 frontend"

    echo "  Frontend zdeployowany."
}

# --- Health check ---
health_check() {
    echo ""
    echo "--- Health Check ---"
    ssh "${SPARK_IP}" "
        echo 'Backend:';
        curl -s http://127.0.0.1:8083/docs | head -1;
        echo '';
        echo 'Frontend:';
        curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000;
        echo '';
    "
}

# --- Main ---
case "$MODE" in
    backend)
        deploy_backend
        ;;
    frontend)
        deploy_frontend
        ;;
    all)
        deploy_backend
        deploy_frontend
        ;;
    help)
        echo "Użycie: bash spark-deploy/deploy.sh [backend|frontend|all]"
        exit 0
        ;;
    *)
        echo "Nieznany tryb: $MODE"
        echo "Użycie: bash spark-deploy/deploy.sh [backend|frontend|all]"
        exit 1
        ;;
esac

# Health check na koncu
health_check

echo ""
echo "============================================"
echo "  Deploy zakonczony sukcesem!"
echo "  Frontend: http://192.168.1.34:3000"
echo "  Backend:  http://192.168.1.34:8083/docs"
echo "============================================"