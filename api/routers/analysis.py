from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx
import database
import models
from schemas import TextRequest
from core.config import settings
from services.text_service import text_service
from services.ai_service import detectar_erros_acentuacao_com_ia, analisar_redacao_completa, get_pontuacao_sugestao

router = APIRouter(prefix="/v2", tags=["analysis"])

@router.post("/check")
async def check_text(request_data: TextRequest, db: Session = Depends(database.get_db)):
    http_client = text_service.get_client()
    if http_client is None:
        raise HTTPException(
            status_code=503,
            detail="LanguageTool não está disponível. Verifique os logs do servidor."
        )

    if not request_data.text or not request_data.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Texto não pode estar vazio."
        )

    try:
        response = await http_client.post(
            f"{settings.LANGUAGETOOL_URL}/v2/check",
            data={
                "text": request_data.text,
                "language": "pt-BR",
                "level": "picky",
                "enabledOnly": "false",
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        formatted_matches = []
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
        
        if settings.ENABLE_LLM and settings.GEMINI_API_KEY:
            erros_acentuacao = await detectar_erros_acentuacao_com_ia(request_data.text, formatted_matches)
            formatted_matches.extend(erros_acentuacao)
        
        num_erros = len(formatted_matches)
        
        response_json = {
            "original_text": request_data.text,
            "corrections_found": num_erros,
            "matches": formatted_matches,
            "ai_enabled": settings.ENABLE_LLM and bool(settings.GEMINI_API_KEY),
            "ai_ready": num_erros == 0,
            "suggestion": "Corrija os erros básicos e clique em 'Análise Completa com IA' para obter análise detalhada" if num_erros > 0 else None
        }
        
        try:
            db_redacao = models.Redacao(
                tema=request_data.theme,
                texto=request_data.text
            )
            db.add(db_redacao)
            db.commit()
            db.refresh(db_redacao)

            db_feedback = models.Feedback(
                redacao_id=db_redacao.id,
                dados_correcao=response_json
            )
            db.add(db_feedback)
            db.commit()
        except Exception as db_err:
            print(f"Erro ao salvar no banco de dados em check_text: {db_err}")

        return response_json
        
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout ao conectar ao LanguageTool. Tente novamente.")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Não foi possível conectar ao LanguageTool. Serviço pode estar offline.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Erro do servidor LanguageTool: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.post("/analyze")
async def analyze_with_ai(request_data: TextRequest, db: Session = Depends(database.get_db)):
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="IA não está habilitada. Configure GEMINI_API_KEY."
        )
    
    if not request_data.text or not request_data.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Texto não pode estar vazio."
        )
    
    try:
        http_client = text_service.get_client()
        if http_client is None:
            raise HTTPException(
                status_code=503,
                detail="LanguageTool não está disponível."
            )
        
        response = await http_client.post(
            f"{settings.LANGUAGETOOL_URL}/v2/check",
            data={
                "text": request_data.text,
                "language": "pt-BR",
                "level": "picky",
                "enabledOnly": "false",
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        formatted_matches = []
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
        
        if settings.ENABLE_LLM and settings.GEMINI_API_KEY:
            erros_acentuacao = await detectar_erros_acentuacao_com_ia(request_data.text, formatted_matches)
            formatted_matches.extend(erros_acentuacao)
        
        num_erros = len(formatted_matches)
        
        print("Iniciando análise completa com IA...")
        ai_analysis = await analisar_redacao_completa(request_data.text, formatted_matches, request_data.theme)
        llm_punctuation_suggestion = None
        
        if num_erros == 0:
            llm_punctuation_suggestion = await get_pontuacao_sugestao(request_data.text)
        
        response_json = {
            "original_text": request_data.text,
            "corrections_found": num_erros,
            "matches": formatted_matches,
            "llm_punctuation_suggestion": llm_punctuation_suggestion,
            "ai_analysis": ai_analysis,
            "ai_used": bool(ai_analysis or llm_punctuation_suggestion),
            "ai_ready": num_erros == 0
        }
        
        try:
            db_redacao = models.Redacao(
                tema=request_data.theme,
                texto=request_data.text
            )
            db.add(db_redacao)
            db.commit()
            db.refresh(db_redacao)

            db_feedback = models.Feedback(
                redacao_id=db_redacao.id,
                dados_correcao=response_json
            )
            db.add(db_feedback)
            db.commit()
        except Exception as db_err:
            print(f"Erro ao salvar no banco de dados em analyze_with_ai: {db_err}")

        return response_json
        
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout ao conectar ao LanguageTool.")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="LanguageTool offline.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
