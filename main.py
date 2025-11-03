from fastapi import FastAPI, HTTPException
from schemas import TextRequest
import uvicorn
import httpx
import os
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware


LANGUAGETOOL_URL = os.getenv("LANGUAGETOOL_URL", "http://127.0.0.1:8010")
LANGUAGETOOL_TIMEOUT = float(os.getenv("LANGUAGETOOL_TIMEOUT", "30.0"))

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
    try:
        if http_client is None:
            return {"status": "unhealthy", "reason": "HTTP client not initialized"}
        
        # Testa conexão com LanguageTool
        response = await http_client.get(
            f"{LANGUAGETOOL_URL}/v2/languages",
            timeout=5.0
        )
        
        if response.status_code == 200:
            return {"status": "healthy", "languagetool": "connected"}
        else:
            return {"status": "degraded", "languagetool": f"status {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "reason": str(e)}

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
    if http_client is not None:
        await http_client.aclose()
        http_client = None

@app.post("/v2/check")
async def check_text(request_data: TextRequest):
    """ Recebe o texto e verifica erros gramaticais usando LanguageTool. """
    
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
            "matches": formatted_matches
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