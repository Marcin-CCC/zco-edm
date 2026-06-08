# =====================================================
# EDM ZCO - Deploy to Spark (PowerShell version)
# =====================================================
# Skrypt kopiujacy lokalne zmiany na Spark
# Użycie: pwsh -File spark-deploy/deploy.ps1 [backend|frontend|all]
# =====================================================

$SPARK_DIR = "/home/marcin/zco-edm-app"
$SPARK_IP = "spark"  # alias SSH w ~/.ssh/config
$MODE = if ($args.Count -gt 0) { $args[0] } else { "all" }

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  EDM ZCO - Deploy to Spark" -ForegroundColor Cyan
Write-Host "  Mode: $MODE" -ForegroundColor Cyan
Write-Host "  Target: ${SPARK_IP}:${SPARK_DIR}" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# --- Deploy Backend ---
function Deploy-Backend {
    Write-Host ""
    Write-Host "--- Deploying Backend ---" -ForegroundColor Yellow

    # Kopiuj Dockerfile
    Write-Host "  Kopiowanie Dockerfile..."
    scp backend/Dockerfile "${SPARK_IP}:${SPARK_DIR}/backend/Dockerfile"

    # Kopiuj requirements.txt
    Write-Host "  Kopiowanie requirements.txt..."
    scp backend/requirements.txt "${SPARK_IP}:${SPARK_DIR}/backend/requirements.txt"

    # Kopiowac cala strukture modułów backendu
    Write-Host "  Kopiowanie kodu backend..."
    scp -r backend/app/* "${SPARK_IP}:${SPARK_DIR}/backend/app/"

    # Kopiuj seed.sql
    Write-Host "  Kopiowanie seed.sql..."
    scp backend/seed.sql "${SPARK_IP}:${SPARK_DIR}/backend/seed.sql"

    # Kopiuj pliki konfiguracyjne
    Write-Host "  Kopiowanie .env.spark..."
    scp backend/.env.spark "${SPARK_IP}:${SPARK_DIR}/backend/.env.spark"

    # Kopiuj VERSION, BUILD_DATE, GIT_COMMIT
    Write-Host "  Kopiowanie VERSION..."
    if (Test-Path "VERSION") {
        scp VERSION "${SPARK_IP}:${SPARK_DIR}/VERSION"
    }
    # BUILD_DATE and GIT_COMMIT are generated at Docker build time, not needed locally

    # Rebuild i restart
    Write-Host "  Budowanie i restart backend..."
    ssh "${SPARK_IP}" "cd ${SPARK_DIR} && docker compose -f docker-compose.yaml --profile spark up -d --build backend"

    Write-Host "  Backend zdeployowany." -ForegroundColor Green
}

# --- Deploy Frontend ---
function Deploy-Frontend {
    Write-Host ""
    Write-Host "--- Deploying Frontend ---" -ForegroundColor Yellow

    # Kopiuj Dockerfile
    Write-Host "  Kopiowanie Dockerfile..."
    scp frontend/Dockerfile "${SPARK_IP}:${SPARK_DIR}/frontend/Dockerfile"

    # Kopiuj package.json
    Write-Host "  Kopiowanie package.json..."
    scp frontend/package.json "${SPARK_IP}:${SPARK_DIR}/frontend/package.json"

    # Kopiuj next.config.js
    Write-Host "  Kopiowanie next.config.js..."
    scp frontend/next.config.js "${SPARK_IP}:${SPARK_DIR}/frontend/next.config.js"

    # Kopiuj tsconfig.json
    Write-Host "  Kopiowanie tsconfig.json..."
    scp frontend/tsconfig.json "${SPARK_IP}:${SPARK_DIR}/frontend/tsconfig.json"

    # Kopiuj caly src frontendu
    Write-Host "  Kopiowanie src..."
    scp -r frontend/src/* "${SPARK_IP}:${SPARK_DIR}/frontend/src/"

    # Kopiuj .env.dev
    Write-Host "  Kopiowanie .env.dev..."
    scp frontend/.env.dev "${SPARK_IP}:${SPARK_DIR}/frontend/.env.dev"

    # Rebuild i restart z BACKEND_URL
    Write-Host "  Budowanie i restart frontend..."
    ssh "${SPARK_IP}" "cd ${SPARK_DIR} && docker compose -f docker-compose.yaml --profile spark up -d --build --build-arg BACKEND_URL=http://172.17.0.1:8083 frontend"

    Write-Host "  Frontend zdeployowany." -ForegroundColor Green
}

# --- Health check ---
function Health-Check {
    Write-Host ""
    Write-Host "--- Health Check ---" -ForegroundColor Yellow
    ssh "${SPARK_IP}" "
        echo 'Backend:';
        curl -s --max-time 5 http://127.0.0.1:8083/api/health;
        echo '';
        echo 'Frontend:';
        curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000;
        echo '';
        echo 'Version:';
        curl -s --max-time 5 http://127.0.0.1:8083/api/version;
        echo '';
    "
}

# --- Main ---
switch ($MODE) {
    "backend" {
        Deploy-Backend
        Health-Check
    }
    "frontend" {
        Deploy-Frontend
        Health-Check
    }
    "all" {
        Deploy-Backend
        Deploy-Frontend
        Health-Check
    }
    "help" {
        Write-Host "Użycie: pwsh -File spark-deploy/deploy.ps1 [backend|frontend|all]"
        exit 0
    }
    default {
        Write-Host "Nieznany tryb: $MODE"
        Write-Host "Użycie: pwsh -File spark-deploy/deploy.ps1 [backend|frontend|all]"
        exit 1
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Deploy zakonczony sukcesem!" -ForegroundColor Green
Write-Host "  Frontend: http://192.168.1.34:3000" -ForegroundColor Cyan
Write-Host "  Backend:  http://192.168.1.34:8083/docs" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
