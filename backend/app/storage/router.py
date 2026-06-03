"""
Storage Router - Remote Spark DGX file access

Ten moduł umożliwia backendowi na PC dostęp do plików na Spark DGX przez HTTP.
Backend może:
1. Wgrywać pliki na Spark przez POST /api/storage/upload
2. Pobierać metadane plików przez GET /api/storage/files
3. Pobierać surowe pliki przez GET /api/storage/files/{file_id}/raw
"""

import os
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import List, Dict, Optional

from app.config import settings

router = APIRouter(prefix="/api/storage", tags=["storage"])


def _get_spark_api_base() -> str:
    """Pobierz bazowy URL API na Spark DGX."""
    # Domyślnie: backend na Sparku ma swoje własne API
    # W hybrydowym mode, to jest URL do backendu na Sparku
    return os.getenv("SPARK_STORAGE_API", "http://192.168.1.34:8000")


@router.post("/upload-to-spark")
async def upload_to_spark(
    file: UploadFile = File(...),
    folder: str = Form("default")
):
    """
    Wgraj plik bezpośrednio na Spark DGX.
    
    Backend na PC odbiera plik od frontendu i kopiuje go na Spark.
    """
    spark_api = _get_spark_api_base()
    
    try:
        # Czytaj plik
        content = await file.read()
        
        # Wyślij na Spark
        async with httpx.AsyncClient(timeout=300) as client:
            files = {"file": (file.filename, content, file.content_type)}
            data = {"folder": folder}
            response = await client.post(
                f"{spark_api}/api/files/upload",
                files=files,
                data=data
            )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload to Spark: {response.text}"
            )
        
        return response.json()
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot connect to Spark DGX at {spark_api}"
        )


@router.get("/files")
async def list_spark_files(folder: Optional[str] = None):
    """
    Pobierz listę plików ze Spark DGX.
    """
    spark_api = _get_spark_api_base()
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            params = {"folder": folder} if folder else {}
            response = await client.get(f"{spark_api}/api/files/", params=params)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to list files from Spark: {response.text}"
                )
            
            return response.json()
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot connect to Spark DGX at {spark_api}"
        )


@router.get("/files/{file_id}/raw")
async def get_spark_file_raw(file_id: str):
    """
    Pobierz surowy plik ze Spark DGX.
    
    Endpoint dla n8n - pobiera plik do przetwarzania.
    """
    spark_api = _get_spark_api_base()
    
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(f"{spark_api}/api/files/{file_id}/download")
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to get file from Spark: {response.text}"
                )
            
            return {
                "filename": response.headers.get("filename", "unknown"),
                "content_type": response.headers.get("content-type", "application/octet-stream"),
                "content": response.content
            }
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot connect to Spark DGX at {spark_api}"
        )


@router.get("/health")
async def spark_storage_health():
    """Sprawdź czy Spark DGX jest osiągalny."""
    spark_api = _get_spark_api_base()
    
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{spark_api}/api/health")
            return {
                "spark": "connected",
                "status": response.json()
            }
    except httpx.ConnectError:
        return {
            "spark": "disconnected",
            "url": spark_api
        }