from fastapi import APIRouter, Depends, HTTPException, File as FastAPIFile, UploadFile, Form, Query
from sqlalchemy.orm import Session
import os
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


@router.post("/analyze-image")
async def analyze_image_with_ai(
    image: UploadFile = FastAPIFile(...),
    theme: Optional[str] = Form(None),
    db: Session = Depends(database.get_db)
):
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="IA não está habilitada. Configure GEMINI_API_KEY."
        )
    
    if not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="O arquivo enviado deve ser uma imagem."
        )
        
    try:
        image_bytes = await image.read()
        
        from services.ai_service import analisar_imagem_redacao
        ai_analysis = await analisar_imagem_redacao(image_bytes, image.content_type, theme)
        
        if ai_analysis is None or "erro" in ai_analysis:
            raise HTTPException(
                status_code=422,
                detail=ai_analysis.get("erro") if ai_analysis else "Não foi possível analisar a imagem."
            )
            
        transcricao = ai_analysis.get("texto_transcrito", "")
        pontuacao = ai_analysis.get("pontuacao_estimada", {})
        
        try:
            db_redacao = models.Redacao(
                tema=theme,
                texto=transcricao or "Redação enviada em imagem (sem transcrição legível)"
            )
            db.add(db_redacao)
            db.commit()
            db.refresh(db_redacao)

            db_feedback = models.Feedback(
                redacao_id=db_redacao.id,
                dados_correcao={
                    "original_text": transcricao,
                    "corrections_found": len(ai_analysis.get("exemplos_melhoria", [])),
                    "ai_analysis": ai_analysis,
                    "is_multimodal": True,
                    "pontuacao_estimada": pontuacao
                }
            )
            db.add(db_feedback)
            db.commit()
        except Exception as db_err:
            print(f"Erro ao salvar no banco de dados em analyze_image_with_ai: {db_err}")
            
        return {
            "original_text": transcricao,
            "ai_analysis": ai_analysis,
            "is_multimodal": True,
            "pontuacao_estimada": pontuacao
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar imagem: {str(e)}")


# WhatsApp Webhook Integration

async def download_whatsapp_media(media_id: str, access_token: str) -> Optional[bytes]:
    """Busca os bytes da imagem enviada pelo WhatsApp usando a Graph API da Meta"""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            url_res = await client.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=headers)
            if url_res.status_code != 200:
                print(f"Erro ao obter URL de mídia do WhatsApp: {url_res.text}")
                return None
            media_url = url_res.json().get("url")
            if not media_url:
                return None
            
            download_res = await client.get(media_url, headers=headers)
            if download_res.status_code == 200:
                return download_res.content
            print(f"Erro ao baixar bytes de mídia do WhatsApp: {download_res.text}")
            return None
    except Exception as e:
        print(f"Exceção ao baixar mídia do WhatsApp: {e}")
        return None


async def send_whatsapp_message(to_phone: str, text: str, phone_number_id: str, access_token: str):
    """Envia uma mensagem de texto de volta para o usuário no WhatsApp"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                headers=headers,
                json=payload
            )
            print(f"Resposta de envio WhatsApp: {res.status_code} - {res.text}")
            return res.status_code == 200
    except Exception as e:
        print(f"Exceção ao enviar mensagem de WhatsApp: {e}")
        return False


@router.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """Rota de verificação exigida pela Meta para cadastrar o webhook"""
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "tcc_whatsapp_verify_token")
    if mode and token:
        if mode == "subscribe" and token == verify_token:
            print("✓ Webhook do WhatsApp verificado com sucesso.")
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(content=challenge)
        else:
            raise HTTPException(status_code=403, detail="Falha na verificação do token.")
    return {"status": "ready"}


@router.post("/webhook/whatsapp")
async def receive_whatsapp_message(request_data: dict, db: Session = Depends(database.get_db)):
    """Recebe mensagens do WhatsApp, detecta imagens e envia feedback detalhado para o aluno"""
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    
    # Valida estrutura básica do payload do WhatsApp Cloud API
    if not request_data or "entry" not in request_data:
        return {"status": "ignored"}
        
    try:
        for entry in request_data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id", "")
                
                for msg in value.get("messages", []):
                    sender_phone = msg.get("from", "")
                    msg_type = msg.get("type", "")
                    
                    if not sender_phone or not phone_number_id:
                        continue
                        
                    if msg_type == "text":
                        # Mensagem informativa de instrução
                        boas_vindas = (
                            "👋 Olá! Sou o Corretor de Redações IA.\n\n"
                            "Para avaliar sua redação, envie uma *foto legível da folha manuscrita*.\n\n"
                            "Vou ler o texto da imagem, calcular suas notas no modelo do ENEM e te dar feedbacks detalhados! 📝"
                        )
                        await send_whatsapp_message(sender_phone, boas_vindas, phone_number_id, access_token)
                        
                    elif msg_type == "image":
                        image_data = msg.get("image", {})
                        media_id = image_data.get("id", "")
                        
                        # Notifica o usuário de que o processamento começou
                        await send_whatsapp_message(
                            sender_phone, 
                            "📥 Imagem recebida! Analisando seu manuscrito, aguarde um momento...", 
                            phone_number_id, 
                            access_token
                        )
                        
                        image_bytes = None
                        mime_type = "image/jpeg"
                        
                        if access_token and media_id:
                            image_bytes = await download_whatsapp_media(media_id, access_token)
                            mime_type = image_data.get("mime_type", "image/jpeg")
                            
                        # Se não houver token configurado ou download falhou em ambiente dev/demo
                        if not image_bytes:
                            # Fallback para fins de demonstração
                            resposta_dev = (
                                "⚠ Não foi possível baixar a imagem enviada. "
                                "Certifique-se de configurar a variável WHATSAPP_ACCESS_TOKEN."
                            )
                            await send_whatsapp_message(sender_phone, resposta_dev, phone_number_id, access_token)
                            continue
                            
                        # Chama a análise multimodal do Gemini
                        from services.ai_service import analisar_imagem_redacao
                        ai_analysis = await analisar_imagem_redacao(image_bytes, mime_type)
                        
                        if not ai_analysis or "erro" in ai_analysis:
                            msg_erro = "❌ Desculpe, não consegui compreender a escrita ou o tema na imagem enviada. Certifique-se de tirar uma foto nítida e bem iluminada."
                            await send_whatsapp_message(sender_phone, msg_erro, phone_number_id, access_token)
                            continue
                            
                        # Estrutura a resposta amigável para envio via WhatsApp
                        transcricao = ai_analysis.get("texto_transcrito", "")
                        pontuacao = ai_analysis.get("pontuacao_estimada", {})
                        total = pontuacao.get("total", 0)
                        nivel = ai_analysis.get("nivel_estimado", "intermediário").upper()
                        
                        # Lista pontos fortes e fracos formatados
                        pontos_fortes = "\n".join([f"• {p}" for p in ai_analysis.get("pontos_fortes", [])]) or "• Nenhum ponto forte listado."
                        pontos_melhoria = "\n".join([f"• {p}" for p in ai_analysis.get("pontos_melhoria", [])]) or "• Nenhum ponto de melhoria listado."
                        sugestoes = "\n".join([f"• {s}" for s in ai_analysis.get("sugestoes_gerais", [])]) or "• Nenhuma sugestão geral."
                        
                        msg_resposta = (
                            f"✨ *Resultado da sua Correção* ✨\n\n"
                            f"📊 *Nota Geral ENEM: {total} / 1000*\n"
                            f"- C1 (Gramática): {pontuacao.get('c1', 0)}\n"
                            f"- C2 (Compreensão): {pontuacao.get('c2', 0)}\n"
                            f"- C3 (Argumentação): {pontuacao.get('c3', 0)}\n"
                            f"- C4 (Coesão): {pontuacao.get('c4', 0)}\n"
                            f"- C5 (Intervenção): {pontuacao.get('c5', 0)}\n\n"
                            f"📈 *Nível do Texto*: {nivel}\n\n"
                            f"✅ *Pontos Fortes*:\n{pontos_fortes}\n\n"
                            f"⚠️ *Pontos de Melhoria*:\n{pontos_melhoria}\n\n"
                            f"💡 *Sugestões Gerais*:\n{sugestoes}\n\n"
                            f"✍️ *Trecho transcrito*: \n\"{transcricao[:300]}...\""
                        )
                        
                        # Salva no histórico do banco de dados
                        try:
                            db_redacao = models.Redacao(
                                tema="WhatsApp Submission",
                                texto=transcricao or f"Envio WhatsApp de {sender_phone}"
                            )
                            db.add(db_redacao)
                            db.commit()
                            db.refresh(db_redacao)

                            db_feedback = models.Feedback(
                                redacao_id=db_redacao.id,
                                dados_correcao={
                                    "sender": sender_phone,
                                    "original_text": transcricao,
                                    "ai_analysis": ai_analysis,
                                    "is_whatsapp": True
                                }
                            )
                            db.add(db_feedback)
                            db.commit()
                        except Exception as db_err:
                            print(f"Erro ao persistir envio do WhatsApp: {db_err}")
                            
                        await send_whatsapp_message(sender_phone, msg_resposta, phone_number_id, access_token)
                        
    except Exception as e:
        print(f"Erro geral no webhook do WhatsApp: {e}")
        
    return {"status": "ok"}


