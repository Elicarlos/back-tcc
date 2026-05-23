from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
import database
import models
import schemas

router = APIRouter(prefix="/classrooms", tags=["classrooms"])

@router.post("", response_model=schemas.ClassroomResponse)
def create_classroom(classroom_in: schemas.ClassroomCreate, db: Session = Depends(database.get_db)):
    nova_turma = models.Classroom(
        name=classroom_in.name,
        school_id=classroom_in.school_id
    )
    db.add(nova_turma)
    db.commit()
    db.refresh(nova_turma)
    return nova_turma

@router.get("", response_model=List[schemas.ClassroomResponse])
def list_classrooms(db: Session = Depends(database.get_db)):
    return db.query(models.Classroom).all()

@router.get("/school/{school_id}", response_model=List[schemas.ClassroomResponse])
def list_classrooms_by_school(school_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Classroom).filter(models.Classroom.school_id == school_id).all()
