from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# Schema pour l'utilisateur
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# Schema pour les tokens
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: dict

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None



# Schema pour les diagnostics
class DiagnosticBase(BaseModel):
    plant: str
    disease: str
    severity: str
    confidence: float = Field(..., ge=0.0, le=1.0)

class DiagnosticCreate(DiagnosticBase):
    image_path: Optional[str] = None
    recommendations: List[str] = []

class DiagnosticHistoryResponse(DiagnosticBase):
    id: int
    date: str
    confidence: int  # Pourcentage
    
    class Config:
        from_attributes = True

# Schema pour le dashboard modifié (sans cultures)
class UserDashboardResponse(BaseModel):
    user_info: dict
    recentDiagnostics: List[DiagnosticHistoryResponse]
    totalDiagnostics: int
    successRate: float