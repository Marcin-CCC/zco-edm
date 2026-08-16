from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models import ROLE_GUEST, DocumentStatus, AccessLevel


# ==================== User ====================
class UserBase(BaseModel):
    email: str
    username: str
    full_name: Optional[str] = None
    role: str = ROLE_GUEST
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # nowe hasło (opcjonalnie; puste = bez zmiany)


class ProfileUpdate(BaseModel):
    """Dane, które użytkownik zmienia SAM SOBIE na stronie Profil.

    Świadomie NIE ma tu roli ani statusu aktywności — te zmienia wyłącznie
    administrator w module Użytkownicy. Inaczej każdy mógłby nadać sobie
    uprawnienia administratora.
    """
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    """Zmiana własnego hasła — zawsze za potwierdzeniem aktualnym hasłem."""
    current_password: str
    new_password: str


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
    # Kategoria zastąpiła status w tabeli plików: status ma znaczenie w kolejce
    # przetwarzania, a na liście dokumentów użytkownik szuka rodzaju dokumentu.
    doc_type: Optional[str] = None
    original_filename: Optional[str] = None
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
    # Kod roli, nie enum: słownik ról jest w bazie, a poprawność kodu sprawdza
    # warstwa routera (rola musi istnieć w tabeli `roles`).
    role: str
    access_level: AccessLevel


class FolderPermissionCreate(FolderPermissionBase):
    folder_id: int


class FolderPermissionResponse(BaseModel):
    id: int
    folder_id: int
    role: str
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
    # users tylko dla administratora — zwykły użytkownik nie dostaje liczby kont
    users: Optional[int] = None
    documents: int
    folders: int
    processed: int


# ==================== Settings ====================
class SettingsResponse(BaseModel):
    n8n_webhook_url: str
    chat_webhook_url: str = ""
    allowed_extensions: str = ""  # dozwolone rozszerzenia, np. "pdf,docx,xlsx"
    idle_timeout_minutes: int = 15  # auto-wylogowanie po bezczynności (frontend)


class SettingsUpdate(BaseModel):
    n8n_webhook_url: Optional[str] = None
    chat_webhook_url: Optional[str] = None
    allowed_extensions: Optional[str] = None
    idle_timeout_minutes: Optional[int] = None


# ==================== Chat ====================
class ChatRequest(BaseModel):
    message: str
    session_id: str
    request_id: Optional[str] = None  # identyfikator pojedynczego pytania (dla źródeł)
    # Zawężenie wyszukiwania treści do wskazanych dokumentów — gdy pytanie dotyczy
    # dokumentów ustalonych wcześniej (rejestr pól albo poprzednia odpowiedź).
    # Uprawnienia do folderów obowiązują niezależnie: oba warunki łączymy w `must`.
    file_ids: Optional[list[int]] = None
    # Czy wolno użyć historii rozmowy (do rozwinięcia pytania i jako kontekst dla
    # modelu). Fałsz = pytanie zadajemy „na czysto". Frontend ustawia to przy jednym
    # ponowieniu, gdy odpowiedź z historią była odmową: zmierzone, że po zmianie
    # tematu w wątku model odmawia, choć to samo pytanie w świeżym wątku działa.
    use_history: bool = True


class ChatSourceItem(BaseModel):
    filename: Optional[str] = None
    page: Optional[int] = None
    score: Optional[float] = None
    file_id: Optional[int] = None
    url: Optional[str] = None
    # Faza B (#7): typ dokumentu i kluczowe pole — czytelniejsza etykieta źródła
    doc_type: Optional[str] = None
    doc_type_name: Optional[str] = None
    # Czy model przywołał ten fragment znacznikiem [Źródło N] w treści odpowiedzi.
    # n8n przysyła teraz WSZYSTKIE fragmenty podane modelowi, także nieprzywołane —
    # bez nich nie da się prześledzić, na czym oparta jest odpowiedź.
    cited: Optional[bool] = None
    doc_key: Optional[str] = None


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


class OcenaCreate(BaseModel):
    """Ocena odpowiedzi wystawiona przez użytkownika pod bąbelkiem czatu.

    `request_id` wiąże ocenę z migawką planu wyszukiwania (pamięć procesu, TTL),
    dzięki czemu zgłoszenie niesie kontekst, a nie samą treść.
    """
    message_id: Optional[int] = None
    request_id: Optional[str] = None
    ocena: str                      # dobra | neutralna | zla
    powod: Optional[str] = None     # tylko przy ocenie negatywnej
    pytanie: Optional[str] = None
    odpowiedz: Optional[str] = None


# ==================== Rejestr schematów typów dokumentów (#7B-2) ====================
class DocTypeField(BaseModel):
    name: str                       # np. "dostawca"
    type: str                       # string | number | date | enum:PLN,EUR,...
    hint: Optional[str] = None      # podpowiedź dla ekstrakcji


class DocTypeSchemaBase(BaseModel):
    slug: str                       # np. "umowa" (unikalne, [a-z0-9_-])
    name: str                       # "Umowa"
    criteria: Optional[str] = None  # kryteria klasyfikacji (dla promptu)
    fields: list[DocTypeField] = []
    # Wzorzec nazwy pliku, np. „{typ}-nr-{numer}-{data}"; pusty = bez generowania
    name_pattern: Optional[str] = None
    active: bool = True


class DocTypeSchemaResponse(DocTypeSchemaBase):
    id: int

    model_config = {"from_attributes": True}


# ==================== Role ====================
class RoleResponse(BaseModel):
    """Rola widziana przez interfejs. `users_count` i `permissions_count` jadą razem
    ze słownikiem, bo okno usuwania roli musi pokazać skutki, zanim ktoś kliknie."""
    code: str
    name: str
    is_system: bool
    sort_order: int
    users_count: int = 0
    permissions_count: int = 0


class RoleCreate(BaseModel):
    name: str
    # Kod roli, z której skopiować uprawnienia do folderów. Bez tego nowa rola
    # nie ma dostępu do niczego.
    copy_permissions_from: Optional[str] = None


class RoleRename(BaseModel):
    """Zmieniamy wyłącznie etykietę — kod roli jest niezmienny."""
    name: str

