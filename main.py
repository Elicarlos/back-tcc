from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import database
import models
from core.config import settings
from services.text_service import text_service

from api.routers import (
    auth, schools, classrooms, activities,
    essays, themes, analysis
)

app = FastAPI(
    title="Api para o TCC",
    description="API desenvolvida para o Trabalho de Conclusão de Curso (TCC) do curso de Licenciatura em Computação IFPI- Zona Sul.",
    version="1.0.0",
    contact={
        "name": "Elicarlos Ferreira",
        "url": "https://seu-portfolio.com",
        "email": "elicarlosantos_@hotmail.com"
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    try:
        models.Base.metadata.create_all(bind=database.engine)
        print("✓ Tabelas do banco de dados criadas com sucesso.")
        
        db_session = database.SessionLocal()
        try:
            if db_session.query(models.Theme).count() == 0:
                print("Populando banco de dados com temas iniciais do ENEM...")
                temas_iniciais = [
                    {"title": "Desafios para a valorização da herança africana no Brasil", "source": "ENEM 2024"},
                    {"title": "Desafios para o enfrentamento da invisibilidade do trabalho de cuidado realizado pela mulher", "source": "ENEM 2023"},
                    {"title": "Valorização de comunidades e povos tradicionais", "source": "ENEM 2022"},
                    {"title": "Invisibilidade e registro civil: garantia de acesso à cidadania no Brasil", "source": "ENEM 2021"},
                    {"title": "O estigma associado às doenças mentais na sociedade brasileira", "source": "ENEM 2020"},
                    {"title": "Democratização do acesso ao cinema no Brasil", "source": "ENEM 2019"},
                    {"title": "Manipulação do comportamento do usuário pelo controle de dados na internet", "source": "ENEM 2018"},
                    {"title": "Desafios para a formação educacional de surdos no Brasil", "source": "ENEM 2017"},
                    {"title": "Caminhos para combater a intolerância religiosa no Brasil", "source": "ENEM 2016"}
                ]
                for tema_item in temas_iniciais:
                    db_theme = models.Theme(title=tema_item["title"], source=tema_item["source"])
                    db_session.add(db_theme)
                db_session.commit()
                print("✓ Temas iniciais do ENEM cadastrados com sucesso.")
        except Exception as populate_err:
            print(f"⚠ Erro ao popular temas iniciais: {populate_err}")
            db_session.rollback()
        finally:
            db_session.close()
            
    except Exception as db_err:
        print(f"⚠ Erro ao inicializar banco de dados: {db_err}")
    
    # Initialize the HTTP client
    text_service.get_client()
    print(f"Conectando ao servidor LanguageTool ({settings.LANGUAGETOOL_URL})...")

    try:
        response = await text_service.http_client.get(f"{settings.LANGUAGETOOL_URL}/v2/languages", timeout=5.0)
        if response.status_code == 200:
            print("✓ Conectado ao LanguageTool com sucesso.")
        else:
            print(f"⚠ LanguageTool respondeu com status {response.status_code}")
    except Exception as e:
        print(f"⚠ AVISO: Falha no teste de conexão com o LanguageTool: {e}")

@app.on_event("shutdown")
async def shutdown():
    print("Servidor FastAPI desligando...")
    try:
        await text_service.close_client()
    except Exception as e:
        print(f"Aviso durante shutdown: {e}")

@app.get("/")
async def read_root():
    """ Rota raiz para verificar se a API está funcionando. """
    return {
        "status": "API de verificação de texto online. Use o endpoint POST /v2/check",
        "languagetool_url": settings.LANGUAGETOOL_URL,
        "health": "ok"
    }

@app.get("/health")
async def health_check():
    """ Endpoint de health check para monitoramento. """
    import google.generativeai as genai
    
    health_status = {
        "status": "healthy",
        "services": {}
    }
    
    try:
        if text_service.http_client is None:
            health_status["services"]["languagetool"] = {"status": "unavailable", "reason": "HTTP client not initialized"}
        else:
            response = await text_service.http_client.get(
                f"{settings.LANGUAGETOOL_URL}/v2/languages",
                timeout=5.0
            )
            if response.status_code == 200:
                health_status["services"]["languagetool"] = {"status": "connected", "url": settings.LANGUAGETOOL_URL}
            else:
                health_status["services"]["languagetool"] = {"status": "degraded", "status_code": response.status_code}
    except Exception as e:
        health_status["services"]["languagetool"] = {"status": "unavailable", "error": str(e)}
        health_status["status"] = "degraded"
    
    try:
        if not settings.ENABLE_LLM:
            health_status["services"]["gemini"] = {"status": "disabled", "reason": "ENABLE_LLM=false"}
        elif not settings.GEMINI_API_KEY:
            health_status["services"]["gemini"] = {
                "status": "unavailable",
                "error": "GEMINI_API_KEY não configurada",
                "suggestion": "Configure a variável de ambiente GEMINI_API_KEY"
            }
            health_status["status"] = "degraded"
        else:
            try:
                models_api = genai.list_models()
                health_status["services"]["gemini"] = {
                    "status": "connected",
                    "model_configured": settings.GEMINI_MODEL,
                    "api_available": True
                }
            except Exception as e:
                health_status["services"]["gemini"] = {
                    "status": "degraded",
                    "error": str(e),
                    "model_configured": settings.GEMINI_MODEL
                }
                health_status["status"] = "degraded"
    except Exception as e:
        health_status["services"]["gemini"] = {"status": "unavailable", "error": str(e)}
        health_status["status"] = "degraded"
    
    return health_status

# Registrando os routers
app.include_router(auth.router)
app.include_router(schools.router)
app.include_router(classrooms.router)
app.include_router(activities.router)
app.include_router(essays.router)
app.include_router(themes.router)
app.include_router(analysis.router)

if __name__ == "__main__":
    print("Iniciando o servidor FastAPI... em http://0.0.0.0:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)