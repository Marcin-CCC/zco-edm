#!/bin/bash
# =====================================================
# EDM ZCO - Deploy Script for Spark DGX
# =====================================================
# Ten skrypt deployuje cala aplikacje na Spark DGX
# Katalog docelowy: /home/marcin/zco-edm-app/

set -e

APP_DIR="/home/marcin/zco-edm-app"
SPARK_HOST="spark"

echo "=== EDM ZCO Deploy to Spark ==="

# Krok 1: Stworzenie struktury katalogow
echo "[1/6] Creating directory structure..."
ssh $SPARK_HOST "mkdir -p $APP_DIR/{backend,frontend,docling,shared_docs/{uploads,processed,archive},postgres-data/data,workflows,spark-deploy}"

# Krok 2: Usuniecie starych kontenerow
echo "[2/6] Removing old containers..."
ssh $SPARK_HOST "docker stop edm-backend-spark 2>/dev/null; docker rm edm-backend-spark 2>/dev/null; true"
ssh $SPARK_HOST "docker stop edm-frontend-spark 2>/dev/null; docker rm edm-frontend-spark 2>/dev/null; true"
ssh $SPARK_HOST "docker stop edm-docling-spark 2>/dev/null; docker rm edm-docling-spark 2>/dev/null; true"

# Krok 3: Wgranie plikow
echo "[3/6] Uploading files..."
scp -r backend/* $SPARK_HOST:$APP_DIR/backend/
scp -r frontend/* $SPARK_HOST:$APP_DIR/frontend/
scp -r docling/* $SPARK_HOST:$APP_DIR/docling/
scp docker-compose.yaml $SPARK_HOST:$APP_DIR/
scp backend/.env.spark $SPARK_HOST:$APP_DIR/
scp -r spark-deploy/* $SPARK_HOST:$APP_DIR/spark-deploy/

# Krok 3.5: Uaktualnienie .env.spark z poprawnymi adresami
echo "[3.5] Updating .env.spark with correct addresses..."
ssh $SPARK_HOST "printf 'DATABASE_URL=postgresql+psycopg2://postgres:tajne_haslo@edm-zco-postgres:5432/edmdatabase\n' > $APP_DIR/.env.spark"
ssh $SPARK_HOST "tail -n +2 $APP_DIR/.env.spark | grep -v '^DATABASE_URL=' >> $APP_DIR/.env.spark.tmp"
ssh $SPARK_HOST "cat $APP_DIR/.env.spark.tmp > $APP_DIR/.env.spark && rm $APP_DIR/.env.spark.tmp"

# Krok 4: Build i deploy backendu
echo "[4/6] Building and deploying backend..."
ssh $SPARK_HOST "cd $APP_DIR/backend && docker build -t edm-backend-spark:latest . && \
  docker stop edm-backend-spark 2>/dev/null; docker rm edm-backend-spark 2>/dev/null; true && \
  docker run -d --name edm-backend-spark \
    -p 8082:8000 \
    -v $APP_DIR/shared_docs:/data/shared_docs \
    --env-file $APP_DIR/.env.spark \
    --restart unless-stopped \
    edm-backend-spark:latest"

# Krok 5: Build i deploy frontendu
echo "[5/6] Building and deploying frontend..."
ssh $SPARK_HOST "cd $APP_DIR/frontend && docker build -t edm-frontend-spark:latest . && \
  docker stop edm-frontend-spark 2>/dev/null; docker rm edm-frontend-spark 2>/dev/null; true && \
  docker run -d --name edm-frontend-spark \
    -p 3000:3000 \
    -e NEXT_PUBLIC_API_URL=http://172.17.0.1:8082 \
    --restart unless-stopped \
    edm-frontend-spark:latest"

# Krok 6: Status
echo "[6/6] Deployment complete!"
echo ""
echo "Services running on Spark:"
ssh $SPARK_HOST "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'backend|frontend|postgres|docling'"
echo ""
echo "Access points:"
echo "  Frontend: http://192.168.1.34:3000"
echo "  Backend API: http://192.168.1.34:8082/docs"
echo "  Docling: http://192.168.1.34:8002/api/parse"
echo "  PostgreSQL: port 5433"
