from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database
import models
import schemas
from core.security import obter_hash_senha, verificar_senha
import httpx
import uuid
from core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=schemas.UserResponse)
def register_user(user_in: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
    
    novo_usuario = models.User(
        name=user_in.name,
        email=user_in.email,
        password_hash=obter_hash_senha(user_in.password),
        role=user_in.role,
        school_id=user_in.school_id,
        classroom_id=user_in.classroom_id
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario

@router.post("/login", response_model=schemas.UserResponse)
def login_user(login_in: schemas.UserLogin, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == login_in.email).first()
    if not user or not verificar_senha(login_in.password, user.password_hash):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos.")
    return user

@router.post("/google", response_model=schemas.UserResponse)
async def google_login(google_in: schemas.UserGoogleLogin, db: Session = Depends(database.get_db)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": google_in.credential}
            )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao conectar com servidor de autenticação do Google: {str(e)}"
        )
    
    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Token do Google inválido ou expirado."
        )
    
    payload = response.json()
    google_aud = payload.get("aud")
    if settings.GOOGLE_CLIENT_ID and google_aud != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail="Audiência do token do Google não corresponde ao Client ID configurado."
        )
        
    email = payload.get("email")
    name = payload.get("name") or email.split("@")[0]
    
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível obter o e-mail do token do Google."
        )
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        senha_aleatoria = str(uuid.uuid4())
        user = models.User(
            name=name,
            email=email,
            password_hash=obter_hash_senha(senha_aleatoria),
            role="student"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    return user
