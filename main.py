from fastapi import FastAPI, HTTPException
from schemas import TextRequest
import uvicorn
import httpx
import os
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware


LANGUAGETOOL_URL = os.getenv("LANGUAGETOOL_URL", "http://127.0.0.1:8010")
LANGUAGETOOL_TIMEOUT = float(os.getenv("LANGUAGETOOL_TIMEOUT", "30.0"))


HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")  # Opcional, pode usar sem chave com limites menores
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "pierreguillou/gpt2-small-portuguese")
HUGGINGFACE_API_URL = f"https://api-inference.huggingface.co/models/{HUGGINGFACE_MODEL}" 
ENABLE_LLM = os.getenv("ENABLE_LLM", "true").lower() == "true"


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
    allow_origins=[
        "http://localhost:5173",  # Porta padrão do Vite
        "http://localhost:3000",  # Porta alternativa do React
        "http://127.0.0.1:5173",   # Alternativa com 127.0.0.1
        "http://127.0.0.1:3000",
        
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos os headers
)



http_client: Optional[httpx.AsyncClient] = None


async def get_pontuacao_sugestao(text: str):
    """ Usa LLM para sugerir pontuação """
    if not ENABLE_LLM:
        print("LLM desabilitado (ENABLE_LLM=false)")
        return None
    
    print(f"Chamando a Huggin Face API (modelo: {HUGGINGFACE_MODEL})")
    
    prompt = f"""Você é um especialista em pontuação em português.
    Analise o texto e sugira onde adicionar vírgulas e pontos para melhorar a clareza.
    Responda APENAS com o texto corrigido, sem explicações.

    Texto: {text}
    Correção:"""

    try: 
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {}

            if HUGGINGFACE_API_KEY:
                headers["Autorization"] = f"Bearer { HUGGINGFACE_API_KEY}"

            print(f"Enviando a requisçao para a Hugging Face ....")
            response = await client.post(
                HUGGINGFACE_API_URL,
                 json={
                    "inputs": prompt,
                    "paramenters": {
                        "max_new_tokens": 500,
                        "temperature": 0.3,
                        "return_full_text": False                     
                    }
                }
            )
            # Verificar status antes de processar
            if response.status_code != 200:
                error_text = response.text[:300] if response.text else "Sem detalhes"
                print(f"ERRO {response.status_code} do Ollama: {error_text}")
                if response.status_code == 500:
                    print(f"Erro 500 geralmente indica que o modelo '{OLLAMA_MODEL}' não foi baixado.")
                    print(f"   Execute no terminal: ollama pull {OLLAMA_MODEL}")
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        print(f"   Detalhes: {error_json['error']}")
                except:
                    pass
                return None
            
            response.raise_for_status()
            result = response.json()
            suggestion = result.get("response", "").strip()
            
            if suggestion:
                print(f"LLM retornou sugestão: {suggestion[:100]}...")  # Primeiros 100 caracteres
            else:
                print("LLM retornou resposta vazia")
            
            return suggestion
    except httpx.ConnectError:
        print(f"ERRO: Não foi possível conectar ao Ollama em {OLLAMA_URL}")
        print(f"   Verifique se o Ollama está rodando: ollama serve")
        return None
    except httpx.TimeoutException:
        print(f"ERRO: Timeout ao chamar Ollama (mais de 15 segundos)")
        return None
    except Exception as e:
        print(f"Erro ao obter pontuação sugerida: {e}")
        return None

@app.get("/")
async def read_root():
    """ Rota raiz para verificar se a API está funcionando. """
    return {
        "status": "API de verificação de texto online. Use o endpoint POST /v2/check",
        "languagetool_url": LANGUAGETOOL_URL,
        "health": "ok"
    }

@app.get("/health")
async def health_check():
    """ Endpoint de health check para monitoramento. """
    health_status = {
        "status": "healthy",
        "services": {}
    }
    
    # Verificar LanguageTool
    try:
        if http_client is None:
            health_status["services"]["languagetool"] = {"status": "unavailable", "reason": "HTTP client not initialized"}
        else:
            response = await http_client.get(
                f"{LANGUAGETOOL_URL}/v2/languages",
                timeout=5.0
            )
            if response.status_code == 200:
                health_status["services"]["languagetool"] = {"status": "connected", "url": LANGUAGETOOL_URL}
            else:
                health_status["services"]["languagetool"] = {"status": "degraded", "status_code": response.status_code}
    except Exception as e:
        health_status["services"]["languagetool"] = {"status": "unavailable", "error": str(e)}
        health_status["status"] = "degraded"
    
    # Verificar Ollama (LLM)
    try:
        if not ENABLE_LLM:
            health_status["services"]["ollama"] = {"status": "disabled", "reason": "ENABLE_LLM=false"}
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{OLLAMA_URL}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]
                    health_status["services"]["ollama"] = {
                        "status": "connected",
                        "url": OLLAMA_URL,
                        "model_configured": OLLAMA_MODEL,
                        "models_available": model_names
                    }
                else:
                    health_status["services"]["ollama"] = {"status": "degraded", "status_code": response.status_code}
                    health_status["status"] = "degraded"
    except httpx.ConnectError:
        health_status["services"]["ollama"] = {
            "status": "unavailable",
            "error": f"Não foi possível conectar em {OLLAMA_URL}",
            "suggestion": "Verifique se o Ollama está rodando: ollama serve"
        }
        health_status["status"] = "degraded"
    except Exception as e:
        health_status["services"]["ollama"] = {"status": "unavailable", "error": str(e)}
        health_status["status"] = "degraded"
    
    return health_status

@app.on_event("startup")
async def startup_event():
    """ 
    Esta função é executada quando a aplicação inicia.
    Cria cliente HTTP reutilizável e verifica conectividade com LanguageTool.
    """
    global http_client
    
    print(f"Conectando ao servidor LanguageTool ({LANGUAGETOOL_URL})...")

    try:
        # Cria cliente HTTP reutilizável (melhor performance)
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(LANGUAGETOOL_TIMEOUT),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        
        # Testa conectividade
        response = await http_client.get(f"{LANGUAGETOOL_URL}/v2/languages", timeout=5.0)
        
        if response.status_code == 200:
            print("✓ Conectado ao LanguageTool com sucesso.")
        else:
            print(f"⚠ LanguageTool respondeu com status {response.status_code}")
            
    except httpx.ConnectError:
        print(f"✗ ERRO: Não foi possível conectar ao LanguageTool em {LANGUAGETOOL_URL}")
        print(f"Verifique se o contêiner Docker 'erikvl87/languagetool' está rodando.")
        http_client = None
    except Exception as e:
        print(f"✗ ERRO: Falha ao inicializar cliente HTTP: {e}")
        http_client = None

@app.on_event("shutdown")
async def shutdown():
    """ Esta função é executada para desligar o servidor. """
    global http_client
    
    print("Servidor FastAPI desligando...")
    try:
        if http_client is not None:
            await http_client.aclose()
            http_client = None
    except Exception as e:
        print(f"Aviso durante shutdown: {e}")

@app.post("/v2/check")
async def check_text(request_data: TextRequest):
    """ Recebe o texto e verifica erros gramaticais usando LanguageTool. """

    llm_suggestions = None
    if ENABLE_LLM:
        llm_suggestions = await get_pontuacao_sugestao(request_data.text)
    
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
            f"{LANGUAGETOOL_URL}/v2/check",
            data={
                "text": request_data.text,
                "language": "pt-BR",
                "level": "picky",
                "enabledRules": "CONCORDANCIA_SER_PLURAL"               
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        
        formatted_matches = []
        for match in data.get("matches", []):
            formatted_matches.append({
                "message": match.get("message", ""),
                "replacements": match.get("replacements", []),
                "offset": match.get("offset", 0),
                "length": match.get("length", 0),
                "ruleId": match.get("rule", {}).get("id", ""),
                "context": match.get("context", {}),
            })

        return {
            "original_text": request_data.text,
            "corrections_found": len(formatted_matches),
            "matches": formatted_matches,
            "llm_punctuation_suggestion": llm_suggestions
        }
        
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timeout ao conectar ao LanguageTool. Tente novamente."
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível conectar ao LanguageTool. Serviço pode estar offline."
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro do servidor LanguageTool: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )

if __name__ == "__main__":
    print("Iniciando o servidor FastAPI... em http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)