import os
import requests
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ---------------------------------------------------------
# KONFIGURACJA ŚRODOWISKA I ZMIENNE
# ---------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:tajne_haslo@postgres:5432/edmdatabase")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://192.168.1.34:5678/webhook/document-uploaded")

# Zgodnie z docker-compose.yml, wolumen współdzielony to /data
STORAGE_DIR = "/data"
os.makedirs(STORAGE_DIR, exist_ok=True)

# ---------------------------------------------------------
# KONFIGURACJA BAZY DANYCH (PostgreSQL + SQLAlchemy)
# ---------------------------------------------------------
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Definicja tabeli dokumentów
class DocumentDB(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    folder_path = Column(String) # Np. "/EDM Główny/Procedury ZCO"
    status = Column(String, default="W kolejce (n8n)")
    raw_text = Column(Text, nullable=True) # Tutaj trafi wynik z Docling
    upload_date = Column(DateTime, default=datetime.utcnow)
    chunks_count = Column(Integer, default=0)

# Tworzenie tabel w bazie danych, jeśli nie istnieją
Base.metadata.create_all(bind=engine)

# Zależność (Dependency) wstrzykująca sesję bazy danych
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# APLIKACJA FASTAPI
# ---------------------------------------------------------
app = FastAPI(title="EDM ZCO - Główne API (Backend)")

# Ustawienia CORS (pozwala na połączenie z lokalnego Next.js na Windowsie)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # W produkcji podaj konkretne IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "API EDM ZCO działa poprawnie. Połączono z bazą danych."}

@app.post("/api/upload")
async def upload_document(
    files: List[UploadFile] = File(...),
    folder_path: str = Form("Katalog_Główny"),
    db: Session = Depends(get_db)
):
    """
    Endpoint przyjmujący pliki z interfejsu Next.js.
    Zapisuje plik fizycznie na dysku DGX, dodaje wpis do bazy i powiadamia n8n.
    """
    uploaded_records = []

    for file in files:
        # 1. Budowa ścieżki i zapis na współdzielony dysk (/data)
        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(STORAGE_DIR, safe_filename)
        
        try:
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Błąd zapisu pliku: {str(e)}")

        # 2. Zapis metadanych do bazy PostgreSQL
        new_doc = DocumentDB(
            filename=safe_filename,
            file_path=file_path,
            folder_path=folder_path,
            status="W kolejce (n8n)"
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        uploaded_records.append(new_doc)

        # 3. Wysłanie powiadomienia do webhooka n8n
        # Przekazujemy ID z Postgresa, aby n8n mógł zaktualizować status dokumentu!
        try:
            payload = {
                "document_id": new_doc.id,
                "filename": safe_filename,
                "file_path": file_path,
                "folder_path": folder_path
            }
            # Timeout na 3 sekundy, żeby webhook nie blokował odpowiedzi do UI
            requests.post(N8N_WEBHOOK_URL, json=payload, timeout=3)
        except requests.exceptions.RequestException as e:
            print(f"Ostrzeżenie: Nie udało się połączyć z webhookiem n8n: {e}")
            # Zmiana statusu w razie błędu połączenia z n8n
            new_doc.status = "Błąd: Brak połączenia z n8n"
            db.commit()

    return {
        "message": f"Przesłano {len(uploaded_records)} plików.",
        "documents": [{"id": d.id, "name": d.filename, "status": d.status} for d in uploaded_records]
    }

@app.get("/api/documents")
def get_documents(db: Session = Depends(get_db)):
    """ Endpoint pobierający wszystkie dokumenty dla panelu 'Kolejka' i 'RAW Preview' """
    docs = db.query(DocumentDB).order_by(DocumentDB.upload_date.desc()).all()
    return docs