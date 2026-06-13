from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class TextRequest(BaseModel):
    text: str
    theme: Optional[str] = None

# Autenticação e Usuário
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "student" # "admin", "teacher", "student"
    school_id: Optional[int] = None
    classroom_id: Optional[int] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserGoogleLogin(BaseModel):
    credential: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    quota_limit: int
    quota_used: int
    school_id: Optional[int] = None
    classroom_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

# Escola
class SchoolCreate(BaseModel):
    name: str

class SchoolResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

# Turma
class ClassroomCreate(BaseModel):
    name: str
    school_id: int

class ClassroomResponse(BaseModel):
    id: int
    name: str
    school_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Atividade
class ActivityCreate(BaseModel):
    theme: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    classroom_id: int
    created_by: int

class ActivityResponse(BaseModel):
    id: int
    theme: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    classroom_id: int
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True

# Redação
class EssayCreate(BaseModel):
    student_id: int
    activity_id: Optional[int] = None
    theme: str
    text: str
    score_c1: int = 0
    score_c2: int = 0
    score_c3: int = 0
    score_c4: int = 0
    score_c5: int = 0
    score_total: int = 0
    correction_json: Optional[str] = None
    teacher_notes: Optional[str] = None

class EssayResponse(BaseModel):
    id: int
    student_id: int
    activity_id: Optional[int] = None
    theme: str
    text: str
    score_c1: int
    score_c2: int
    score_c3: int
    score_c4: int
    score_c5: int
    score_total: int
    teacher_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class EssayDetailResponse(BaseModel):
    id: int
    student_id: int
    activity_id: Optional[int] = None
    theme: str
    text: str
    score_c1: int
    score_c2: int
    score_c3: int
    score_c4: int
    score_c5: int
    score_total: int
    correction_json: Optional[str] = None
    teacher_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Temas
class ThemeCreate(BaseModel):
    title: str
    source: Optional[str] = None

class ThemeResponse(BaseModel):
    id: int
    title: str
    source: Optional[str] = None
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True