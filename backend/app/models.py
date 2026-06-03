from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Float, ForeignKey, Text
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
    size = Column(Float, nullable=True)  # rozmiar w bajtach
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacje
    folder = relationship("Folder", back_populates="files")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="uploaded_files")
