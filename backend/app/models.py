from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class UserRole(str, enum.Enum):
    """Enum ról użytkowników."""
    ADMIN = "admin"
    DOCTOR = "doctor"
    MEDICAL_STAFF = "medical_staff"
    TECHNICIAN = "technician"
    OFFICE_STAFF = "office_staff"
    GUEST = "guest"


class DocumentStatus(str, enum.Enum):
    """Statusy dokumentów/plików."""
    PENDING = "W kolejce (n8n)"
    PARSING = "Parsowanie (Docling)"
    PENDING_CHUNKING = "Chunkowanie"
    PENDING_VECTORIZE = "Wektoryzacja (Qdrant)"
    READY = "Przetworzono"
    ERROR = "Błąd przetwarzania"


class AccessLevel(str, enum.Enum):
    """Poziomy dostępu do folderów."""
    READ = "read"
    WRITE = "write"


class User(Base):
    """Tabela użytkowników systemu."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.GUEST, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relacje
    uploaded_files = relationship("File", foreign_keys="File.uploaded_by", back_populates="uploader")


class Folder(Base):
    """Tabela folderów z hierarchią."""
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    path = Column(String(1000), nullable=False, unique=True)  # np. /dokumenty/medyczne
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    description = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacje
    parent = relationship("Folder", remote_side=[id], backref="children")
    permissions = relationship("FolderPermission", back_populates="folder")
    files = relationship("File", back_populates="folder")


class FolderPermission(Base):
    """Uprawnienia RBAC dla folderów."""
    __tablename__ = "folder_permissions"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    access_level = Column(Enum(AccessLevel), nullable=False)

    # Relacje
    folder = relationship("Folder", back_populates="permissions")


class File(Base):
    """Tabela plików."""
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # ścieżka do pliku na dysku
    mime_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=True)  # rozmiar w bajtach
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    ocr_result = Column('ocr_result', Text, nullable=True)  # wynik OCR z Docling (nazwa kolumny w DB: ocr_result)
    metadata_ = Column('metadata', JSON, nullable=True)  # dodatkowe metadane (JSON) — SQLAlchemy rezerwuje 'metadata'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacje
    folder = relationship("Folder", back_populates="files")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="uploaded_files")


# ==================== Future Processing Tables ====================
# These models correspond to tables created in seed.sql for document processing pipeline.
# They will be used when the full processing/RAG pipeline is implemented.


class Document(Base):
    """Tabela dokumentów - dla pełnego pipeline'u przetwarzania (Docling, Qdrant)."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    folder_path = Column(String(500), nullable=True)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    status = Column(String(50), default="pending")
    raw_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    chunks_count = Column(Integer, default=0)
    vector_id = Column(String(255), nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    meta_data = Column(JSON, nullable=True)

    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    folder = relationship("Folder")
    uploader = relationship("User")


class DocumentPage(Base):
    """Strona dokumentu - wyniki parsowania."""
    __tablename__ = "document_pages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    content = Column(JSON, nullable=True)
    raw_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="pages")


class ProcessingQueue(Base):
    """Kolejka przetwarzania dokumentów."""
    __tablename__ = "processing_queue"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    status = Column(String(50), default="pending")
    priority = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Embedding(Base):
    """Wektoryzacja treści dokumentu dla Qdrant."""
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    page_number = Column(Integer, nullable=True)
    vector_id = Column(Integer, nullable=True)
    content = Column(Text, nullable=True)
    meta_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    """Logi zdarzeń użytkownika."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Logi audytowe operacji systemu."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    """Tabela ustawień aplikacji."""
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True, index=True)
    value = Column(Text, nullable=False, default='')
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
