#!/bin/bash
# =====================================================
# EDM ZCO - Deploy to Spark DGX
# =====================================================
# Skrypt kopiujący lokalne zmiany na Spark
# Użycie: bash spark-deploy/deploy.sh [backend|frontend|all]
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

    # Kopiuj nowy Dockerfile (z --reload)
    echo "  Kopiowanie Dockerfile..."
    scp backend/Dockerfile "${SPARK_IP}:${SPARK_DIR}/backend/Dockerfile"

    # Kopiuj requirements.txt
    echo "  Kopiowanie requirements.txt..."
    scp backend/requirements.txt "${SPARK_IP}:${SPARK_DIR}/backend/requirements.txt"

    # Kopiuj zmienione moduły (tylko te, które się zmieniły)
    echo "  Kopiowanie kodu backend..."
    scp -r backend/app/* "${SPARK_IP}:${SPARK_DIR}/backend/app/"

    # Rebuild i restart
    echo "  Budowanie i restart backend..."
    ssh "${SPARK_IP}" "cd ${SPARK_DIR} && docker compose --profile spark up -d --build backend"

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

    # Kopiuj entire src
    echo "  Kopiowanie src..."
    scp -r frontend/src/* "${SPARK_IP}:${SPARK_DIR}/frontend/src/"

    # Rebuild i restart (BACKEND_URL musi byc ustawiony dla Spark)
    echo "  Budowanie i restart frontend..."
    ssh "${SPARK_IP}" "cd ${SPARK_DIR} && docker compose --profile spark up -d --build --build-arg BACKEND_URL=http://172.17.0.1:8082 frontend"

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

# Health check na końcu
health_check

echo ""
echo "============================================"
echo "  Deploy zakończony sukcesem!"
echo "  Frontend: http://192.168.1.34:3000"
echo "  Backend:  http://192.168.1.34:8083/docs"
echo "============================================"