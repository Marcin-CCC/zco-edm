from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models import UserRole, DocumentStatus, AccessLevel


# ==================== User ====================
class UserBase(BaseModel):
    email: str
    username: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.GUEST
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # nowe hasło (opcjonalnie; puste = bez zmiany)


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: str
    password: str


class UserInDB(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    email: str
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    last_login: Optional[datetime] = None


# ==================== File ====================
class FileBase(BaseModel):
    filename: str
    folder_id: Optional[int] = None


class FileCreate(FileBase):
    pass


class FileResponse(FileBase):
    id: int
    file_path: str
    mime_type: Optional[str] = None
    size: Optional[float] = None
    uploaded_by: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    folder: Optional[dict] = None
    uploader: Optional[dict] = None

    model_config = {"from_attributes": True}


class FileUpdate(BaseModel):
    status: Optional[DocumentStatus] = None
    folder_id: Optional[int] = None


# ==================== Folder ====================
class FolderBase(BaseModel):
    name: str
    parent_id: Optional[int] = None


class FolderCreate(FolderBase):
    pass


class FolderResponse(BaseModel):
    id: int
    name: str
    path: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    can_write: bool = False  # czy bieżący użytkownik ma prawo Zapis w tym folderze
    file_count: int = 0  # liczba plików bezpośrednio w tym folderze

    model_config = {"from_attributes": True}


class FolderTreeResponse(FolderResponse):
    children: list = []

    model_config = {"from_attributes": True}


# ==================== FolderPermission ====================
class FolderPermissionBase(BaseModel):
    role: UserRole
    access_level: AccessLevel


class FolderPermissionCreate(FolderPermissionBase):
    folder_id: int


class FolderPermissionResponse(BaseModel):
    id: int
    folder_id: int
    role: UserRole
    access_level: AccessLevel

    model_config = {"from_attributes": True}


# ==================== Auth ====================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None


# ==================== Dashboard ====================
class DashboardStats(BaseModel):
    users: int
    documents: int
    folders: int
    processed: int


# ==================== Settings ====================
class SettingsResponse(BaseModel):
    n8n_webhook_url: str
    chat_webhook_url: str = ""
    allowed_extensions: str = ""  # dozwolone rozszerzenia, np. "pdf,docx,xlsx"


class SettingsUpdate(BaseModel):
    n8n_webhook_url: Optional[str] = None
    chat_webhook_url: Optional[str] = None
    allowed_extensions: Optional[str] = None


# ==================== Chat ====================
class ChatRequest(BaseModel):
    message: str
    session_id: str
    request_id: Optional[str] = None  # identyfikator pojedynczego pytania (dla źródeł)


class ChatSourceItem(BaseModel):
    filename: Optional[str] = None
    page: Optional[int] = None
    score: Optional[float] = None
    file_id: Optional[int] = None
    url: Optional[str] = None


class ChatSourcesPayload(BaseModel):
    request_id: str
    sources: list[ChatSourceItem] = []


# ==================== Historia rozmów ====================
class ConversationCreate(BaseModel):
    title: str  # zwykle pierwsze pytanie (skracane po stronie serwera)


class ConversationSummary(BaseModel):
    id: int
    title: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    role: str
    content: str
    sources: Optional[list] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConversationDetail(BaseModel):
    id: int
    title: str
    messages: list[MessageOut] = []


class TurnCreate(BaseModel):
    """Zapis jednej tury: pytanie użytkownika + odpowiedź asystenta."""
    user_message: str
    assistant_message: str
    sources: Optional[list] = None
