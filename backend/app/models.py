from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base


# ==================== Role użytkowników ====================
# Rola NIE jest enumem w kodzie — administrator zakłada własne role w interfejsie,
# więc słownik ról to dane (tabela `roles`), a `users.role` i `folder_permissions.role`
# trzymają jego `code`. Wcześniej rola była enumem Pythona odwzorowanym na natywny typ
# `userrole` w Postgresie; z takiego typu nie da się usunąć wartości, więc każda
# skasowana rola zostawiałaby po sobie martwą etykietę w schemacie na zawsze.
#
# Kody zapisane w bazie są WIELKIMI literami ("ADMIN", "DOCTOR"), bo tak zapisywał je
# SQLAlchemy dla enuma (nazwa elementu, nie wartość). Zostawiamy je bez zmian:
# przepisanie ich na małe litery zabrałoby możliwość powrotu do poprzedniej wersji
# aplikacji, która potrafi czytać wyłącznie stare kody.
ROLE_ADMIN = "ADMIN"
ROLE_GUEST = "GUEST"

# Role zakładane przy pierwszym starcie. `is_system` = rola, której nie wolno usunąć:
# ADMIN jest wpisany w każdą kontrolę uprawnień, a GUEST jest rolą domyślną nowego
# użytkownika — bez nich aplikacja nie ma się do czego odwołać.
BUILT_IN_ROLES: list[dict] = [
    {"code": ROLE_ADMIN, "name": "Administrator", "is_system": True, "sort_order": 10},
    {"code": "DOCTOR", "name": "Lekarz", "is_system": False, "sort_order": 20},
    {"code": "MEDICAL_STAFF", "name": "Personel medyczny", "is_system": False, "sort_order": 30},
    {"code": "TECHNICIAN", "name": "Technik", "is_system": False, "sort_order": 40},
    {"code": "OFFICE_STAFF", "name": "Personel biurowy", "is_system": False, "sort_order": 50},
    {"code": ROLE_GUEST, "name": "Gość", "is_system": True, "sort_order": 60},
]


class Role(Base):
    """Słownik ról. Kod (`code`) jest identyfikatorem trwałym — to on leży w
    `users.role` i `folder_permissions.role` — więc po utworzeniu roli już się nie
    zmienia. Edytowalna jest wyłącznie `name`, czyli etykieta w interfejsie.
    """
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=100, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentStatus(str, enum.Enum):
    """Statusy dokumentów/plików (uproszczone do 4).

    Przepływ: PENDING → PROCESSING → READY / ERROR
    - PENDING:    plik zapisany na dysku, czeka w kolejce n8n
    - PROCESSING: n8n rozpoczął przetwarzanie (parsowanie/chunki/wektoryzacja)
    - READY:      n8n zakończył przetwarzanie pomyślnie
    - ERROR:      n8n zgłosił błąd lub webhook nie zadziałał
    """
    # UWAGA: w bazie przechowywana jest NAZWA elementu enuma (PENDING/READY/…),
    # a poniższy tekst to wyłącznie etykieta pokazywana w interfejsie i API —
    # jej zmiana nie wymaga migracji danych.
    PENDING = "W kolejce"
    PROCESSING = "Przetwarzanie"
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
    role = Column(String(50), default=ROLE_GUEST, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relacje
    uploaded_files = relationship("File", foreign_keys="File.uploaded_by", back_populates="uploader")

    @property
    def is_admin(self) -> bool:
        """Jedyne miejsce w kodzie, które rozstrzyga „czy administrator".

        Porównanie do stałej, a nie do elementu enuma: po zniknięciu `UserRole`
        każde przeoczone `user.role != UserRole.ADMIN` wysypie się przy imporcie
        modułu, zamiast po cichu odmówić administratorowi dostępu na produkcji.
        """
        return self.role == ROLE_ADMIN


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
    role = Column(String(50), nullable=False)
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


# ==================== Historia rozmów czatu ====================
class Conversation(Base):
    """Pojedyncza rozmowa czatu (jak wątek w ChatGPT).

    sessionId przekazywany do n8n (pamięć LLM) = "{user_id}:{conversation.id}",
    dzięki czemu kontynuacja wątku trafia w ten sam bufor pamięci n8n.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="Nowa rozmowa")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan", order_by="Message.id",
    )


class Message(Base):
    """Pojedyncza wiadomość w rozmowie (user/assistant)."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)  # lista źródeł (tylko dla assistant)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class OcenaOdpowiedzi(Base):
    """Ocena odpowiedzi wystawiona przez użytkownika (kciuk w górę / neutralnie / w dół).

    Po co osobna tabela, a nie kolumny w `messages`: schemat powstaje przez
    `Base.metadata.create_all`, które DODAJE BRAKUJĄCE TABELE, ale nie dodaje kolumn
    do istniejących. Nowa tabela zakłada się więc sama przy starcie, bez ręcznej
    migracji na maszynie klienta.

    Dlaczego trzymamy KOPIE pytania i odpowiedzi zamiast samego `message_id`: ocena ma
    posłużyć za materiał do zestawu kontrolnego (app/retrieval_bench.py), a rozmowy
    użytkownik może skasować. Stąd też `ondelete="SET NULL"` — usunięcie rozmowy nie
    może zabrać ze sobą zgłoszenia o błędnej odpowiedzi.

    `diagnostyka` to migawka planu wyszukiwania (ścieżka, zawężenia, wskazane dokumenty,
    źródła). Bez niej ocena starzeje się w kilka dni: indeks i mechanizmy wyszukiwania
    się zmieniają, więc bez zapisanego kontekstu nie da się już odtworzyć, CO wtedy
    zobaczył model.
    """
    __tablename__ = "oceny_odpowiedzi"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    ocena = Column(String(12), nullable=False)      # dobra | neutralna | zla
    powod = Column(String(40), nullable=True)       # tylko przy ocenie negatywnej
    pytanie = Column(Text, nullable=True)
    odpowiedz = Column(Text, nullable=True)
    diagnostyka = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


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


class DocTypeSchema(Base):
    """Rejestr schematów typów dokumentów (#7B-2).

    Jeden wpis = jeden typ dokumentu. Napędza cztery rzeczy: prompt klasyfikacji,
    prompt ekstrakcji, walidację zapisanych pól oraz tłumaczenie NL→filtr.
    Dodanie nowego typu = nowy wiersz (bez deployu).

    `fields`: lista obiektów [{name, type, hint}], gdzie type ∈
    string|number|date|enum:v1,v2,... — pola płaskie, skalarne, po których się filtruje.
    """
    __tablename__ = "doc_type_schemas"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(50), unique=True, index=True, nullable=False)  # np. "umowa"
    name = Column(String(100), nullable=False)                          # "Umowa"
    criteria = Column(Text, nullable=True)                              # kryteria klasyfikacji
    fields = Column(JSON, nullable=False, default=list)                 # [{name,type,hint}]
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
