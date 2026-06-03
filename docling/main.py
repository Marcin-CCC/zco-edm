import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from docling.document_converter import DocumentConverter

# ---------------------------------------------------------
# APLIKACJA FASTAPI & KONFIGURACJA DOCLING
# ---------------------------------------------------------
app = FastAPI(title="EDM ZCO - Docling OCR Mikroserwis")

# Inicjalizacja parsera Docling.
# Ważne: Przy starcie tego kontenera załadują się w tle modele AI do pamięci GPU (YOLO/LayoutLM).
print("Trwa ładowanie modeli Docling do pamięci maszyn DGX...")
converter = DocumentConverter()
print("Modele załadowane. Docling API jest gotowe.")

class ParseRequest(BaseModel):
    file_path: str  # Oczekiwana ścieżka wewnątrz kontenera, np. "/data/umowa.pdf"
    document_id: int # Opcjonalne ID do logowania procesu

@app.post("/api/parse")
async def parse_document(request: ParseRequest):
    """
    Endpoint wywoływany głównie przez silnik n8n.
    Przyjmuje ścieżkę do pliku, parsuje tabele/tekst i zwraca Markdown.
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=404, 
            detail=f"Brak pliku na dysku współdzielonym: {request.file_path}"
        )
    
    start_time = time.time()
    
    try:
        # Analiza pliku z wykorzystaniem akceleracji maszynowej (GPU)
        result = converter.convert(request.file_path)
        
        # Ekstrakcja do czystego, formatowanego Markdowna.
        # Tabele zostaną zszyte i zaprezentowane w formacie markdown (| kol | kol |)
        markdown_text = result.document.export_to_markdown()
        
        # Ekstrakcja zaawansowanej struktury (jeśli potrzebujesz dokładnych tagów dla chunkingu w n8n)
        document_dict = result.document.export_to_dict()
        
        processing_time = round(time.time() - start_time, 2)
        
        return {
            "status": "success",
            "document_id": request.document_id,
            "file": request.file_path,
            "processing_time_seconds": processing_time,
            "markdown": markdown_text,
            "structure": document_dict
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd analizy Docling: {str(e)}")