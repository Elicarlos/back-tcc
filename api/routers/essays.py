import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
import database
import models
import schemas
from services.ai_service import detectar_erros_acentuacao_com_ia, analisar_redacao_completa, get_pontuacao_sugestao, analisar_redacao_completa_por_competencias
from services.text_service import text_service
from core.config import settings

router = APIRouter(prefix="/essays", tags=["essays"])

@router.post("", response_model=schemas.EssayDetailResponse)
async def create_essay(essay_in: schemas.EssayCreate, db: Session = Depends(database.get_db)):
    student = db.query(models.User).filter(models.User.id == essay_in.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Estudante não encontrado.")
    
    correction_data = None
    if essay_in.correction_json:
        try:
            correction_data = json.loads(essay_in.correction_json)
        except:
            pass
            
    if not correction_data:
        formatted_matches = []
        http_client = text_service.get_client()
        if http_client is not None:
            try:
                response = await http_client.post(
                    f"{settings.LANGUAGETOOL_URL}/v2/check",
                    data={
                        "text": essay_in.text,
                        "language": "pt-BR",
                        "level": "picky",
                        "enabledOnly": "false",
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    for match in data.get("matches", []):
                        formatted_match = {
                            "message": match.get("message", ""),
                            "replacements": match.get("replacements", []),
                            "offset": match.get("offset", 0),
                            "length": match.get("length", 0),
                            "ruleId": match.get("rule", {}).get("id", ""),
                            "context": match.get("context", {}),
                        }
                        formatted_matches.append(formatted_match)
            except Exception as e:
                print(f"Erro LanguageTool em /essays: {e}")
                
        if settings.ENABLE_LLM and settings.GEMINI_API_KEY:
            try:
                erros_acentuacao = await detectar_erros_acentuacao_com_ia(essay_in.text, formatted_matches)
                formatted_matches.extend(erros_acentuacao)
            except Exception as e:
                print(f"Erro em acentuação: {e}")

        num_erros = len(formatted_matches)
        
        ai_analysis = None
        ai_competencies_analysis = None
        if settings.ENABLE_LLM and settings.GEMINI_API_KEY:
            try:
                ai_analysis = await analisar_redacao_completa(essay_in.text, formatted_matches, essay_in.theme)
            except Exception as e:
                print(f"Erro IA antiga: {e}")

            try:
                ai_competencies_analysis = await analisar_redacao_completa_por_competencias(
                    essay_in.text, essay_in.theme, formatted_matches
                )
            except Exception as e:
                print(f"Erro IA competências: {e}")

        llm_punctuation_suggestion = None
        if num_erros == 0 and settings.ENABLE_LLM and settings.GEMINI_API_KEY:
            try:
                llm_punctuation_suggestion = await get_pontuacao_sugestao(essay_in.text)
            except Exception as e:
                print(f"Erro pontuação: {e}")

        correction_data = {
            "original_text": essay_in.text,
            "corrections_found": num_erros,
            "matches": formatted_matches,
            "llm_punctuation_suggestion": llm_punctuation_suggestion,
            "ai_analysis": ai_analysis,
            "ai_competencies_analysis": ai_competencies_analysis,
            "ai_used": bool(ai_analysis or ai_competencies_analysis or llm_punctuation_suggestion),
            "ai_ready": num_erros == 0
        }

    c1, c2, c3, c4, c5 = 120, 120, 120, 120, 120
    pontuacao_estimada = None
    if correction_data and correction_data.get("ai_competencies_analysis"):
        pontuacao_estimada = correction_data["ai_competencies_analysis"].get("pontuacao_estimada")

    if pontuacao_estimada:
        c1 = pontuacao_estimada.get("c1", 120)
        c2 = pontuacao_estimada.get("c2", 120)
        c3 = pontuacao_estimada.get("c3", 120)
        c4 = pontuacao_estimada.get("c4", 120)
        c5 = pontuacao_estimada.get("c5", 120)
    elif correction_data and correction_data.get("ai_analysis") and isinstance(correction_data["ai_analysis"], dict):
        nivel = correction_data["ai_analysis"].get("nivel_estimado", "intermediário").lower()
        if nivel == "avançado":
            c1, c2, c3, c4, c5 = 160, 160, 160, 160, 160
        elif nivel == "básico":
            c1, c2, c3, c4, c5 = 80, 80, 80, 80, 80
            
        num_erros = correction_data.get("corrections_found", 0)
        if num_erros > 15:
            c1 = 40
        elif num_erros > 8:
            c1 = 80
        elif num_erros > 3:
            c1 = 120
        elif num_erros > 0:
            c1 = 160
        else:
            c1 = 200

    score_c1 = essay_in.score_c1 if essay_in.score_c1 > 0 else c1
    score_c2 = essay_in.score_c2 if essay_in.score_c2 > 0 else c2
    score_c3 = essay_in.score_c3 if essay_in.score_c3 > 0 else c3
    score_c4 = essay_in.score_c4 if essay_in.score_c4 > 0 else c4
    score_c5 = essay_in.score_c5 if essay_in.score_c5 > 0 else c5
    score_total = score_c1 + score_c2 + score_c3 + score_c4 + score_c5

    db_essay = models.Essay(
        student_id=essay_in.student_id,
        activity_id=essay_in.activity_id,
        theme=essay_in.theme,
        text=essay_in.text,
        score_c1=score_c1,
        score_c2=score_c2,
        score_c3=score_c3,
        score_c4=score_c4,
        score_c5=score_c5,
        score_total=score_total,
        correction_json=json.dumps(correction_data),
        teacher_notes=essay_in.teacher_notes
    )

    student.quota_used += 1
    db.add(db_essay)
    db.commit()
    db.refresh(db_essay)
    return db_essay

@router.get("/student/{student_id}", response_model=List[schemas.EssayResponse])
def list_essays_by_student(student_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Essay).filter(models.Essay.student_id == student_id).order_by(models.Essay.created_at.desc()).all()

@router.get("/classroom/{classroom_id}", response_model=List[schemas.EssayResponse])
def list_essays_by_classroom(classroom_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Essay).join(models.User, models.Essay.student_id == models.User.id).filter(models.User.classroom_id == classroom_id).order_by(models.Essay.created_at.desc()).all()

@router.get("/{essay_id}", response_model=schemas.EssayDetailResponse)
def get_essay_detail(essay_id: int, db: Session = Depends(database.get_db)):
    essay = db.query(models.Essay).filter(models.Essay.id == essay_id).first()
    if not essay:
        raise HTTPException(status_code=404, detail="Redação não encontrada.")
    return essay

@router.patch("/{essay_id}/notes", response_model=schemas.EssayDetailResponse)
def update_essay_notes(essay_id: int, notes_in: Dict[str, str], db: Session = Depends(database.get_db)):
    essay = db.query(models.Essay).filter(models.Essay.id == essay_id).first()
    if not essay:
        raise HTTPException(status_code=404, detail="Redação não encontrada.")
    
    essay.teacher_notes = notes_in.get("teacher_notes", "")
    db.commit()
    db.refresh(essay)
    return essay
