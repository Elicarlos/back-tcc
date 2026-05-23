from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
import database
import models
import schemas

router = APIRouter(prefix="/activities", tags=["activities"])

@router.post("", response_model=schemas.ActivityResponse)
def create_activity(activity_in: schemas.ActivityCreate, db: Session = Depends(database.get_db)):
    nova_atividade = models.Activity(
        theme=activity_in.theme,
        description=activity_in.description,
        due_date=activity_in.due_date,
        classroom_id=activity_in.classroom_id,
        created_by=activity_in.created_by
    )
    db.add(nova_atividade)
    db.commit()
    db.refresh(nova_atividade)
    return nova_atividade

@router.get("/classroom/{classroom_id}", response_model=List[schemas.ActivityResponse])
def list_activities_by_classroom(classroom_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Activity).filter(models.Activity.classroom_id == classroom_id).all()
