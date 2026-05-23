from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database
import models
import schemas
from core.security import obter_hash_senha, verificar_senha

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
