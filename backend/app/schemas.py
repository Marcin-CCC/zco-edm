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
