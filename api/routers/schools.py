from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
import database
import models
import schemas

router = APIRouter(prefix="/schools", tags=["schools"])

@router.post("", response_model=schemas.SchoolResponse)
def create_school(school_in: schemas.SchoolCreate, db: Session = Depends(database.get_db)):
    nova_escola = models.School(name=school_in.name)
    db.add(nova_escola)
    db.commit()
    db.refresh(nova_escola)
    return nova_escola

@router.get("", response_model=List[schemas.SchoolResponse])
def list_schools(db: Session = Depends(database.get_db)):
    return db.query(models.School).all()
