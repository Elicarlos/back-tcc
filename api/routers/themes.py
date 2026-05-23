from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import database
import models
import schemas

router = APIRouter(prefix="/themes", tags=["themes"])

@router.get("", response_model=List[schemas.ThemeResponse])
def list_themes(db: Session = Depends(database.get_db)):
    return db.query(models.Theme).filter(models.Theme.active == True).order_by(models.Theme.source.desc(), models.Theme.created_at.desc()).all()

@router.post("", response_model=schemas.ThemeResponse)
def create_theme(theme: schemas.ThemeCreate, db: Session = Depends(database.get_db)):
    existing = db.query(models.Theme).filter(models.Theme.title == theme.title).first()
    if existing:
        if not existing.active:
            existing.active = True
            existing.source = theme.source
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Este tema já está cadastrado.")
    
    db_theme = models.Theme(title=theme.title, source=theme.source)
    db.add(db_theme)
    db.commit()
    db.refresh(db_theme)
    return db_theme

@router.delete("/{theme_id}")
def delete_theme(theme_id: int, db: Session = Depends(database.get_db)):
    db_theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not db_theme:
        raise HTTPException(status_code=404, detail="Tema não encontrado.")
    
    db_theme.active = False
    db.commit()
    return {"message": "Tema removido com sucesso."}
