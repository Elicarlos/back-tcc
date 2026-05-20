from fastapi import FastAPI, HTTPException
from schemas import TextRequest
import uvicorn
import httpx
import os
import json
import asyncio
from typing import Optional, Dict, List
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai


def obter_languagetool_url():
    url = os.getenv("LANGUAGETOOL_URL")
    if url:
        return url
    if os.path.exists("/.dockerenv"):
        return "http://languagetool:8010"
    return "http://127.0.0.1:8010"

LANGUAGETOOL_URL = obter_languagetool_url()
LANGUAGETOOL_TIMEOUT = float(os.getenv("LANGUAGETOOL_TIMEOUT", "30.0"))


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyA8wznDIh3Vhi3dgovlCE47Azb1_q6-FCQ")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-pro")
ENABLE_LLM = os.getenv("ENABLE_LLM", "true").lower() == "true"


if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


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
        "http://localhost:5173",  
        "http://localhost:3000",  
        "http://127.0.0.1:5173",   
        "http://127.0.0.1:3000",
        
    ],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)



http_client: Optional[httpx.AsyncClient] = None


_modelo_gemini_cache = None


def listar_modelos_disponiveis():
    """Lista todos os modelos disponíveis na API"""
    try:
        models = genai.list_models()
        modelos_validos = []
        print("Modelos disponíveis na API:")
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                print(f"  - {model.name} (suporta generateContent)")
                modelos_validos.append(model.name)
        return modelos_validos
    except Exception as e:
        print(f"Erro ao listar modelos: {e}")
        return []


def obter_modelo_gemini():
    """Obtém um modelo Gemini válido, tentando vários nomes e testando com uma chamada real"""
    global _modelo_gemini_cache
    

    if _modelo_gemini_cache is not None:
        return _modelo_gemini_cache
    
    
    modelos_disponiveis = listar_modelos_disponiveis()
    
    
    modelos_tentativas = []
    
    
    if modelos_disponiveis:
        # Remove prefixo "models/" se existir e adiciona ambas as versões
        for modelo in modelos_disponiveis[:5]:  # Limita a 5 para não demorar muito
            modelos_tentativas.append(modelo)
            # Tenta também sem o prefixo "models/"
            if modelo.startswith("models/"):
                modelos_tentativas.append(modelo.replace("models/", ""))
    
    # Adiciona modelos padrão como fallback
    modelos_tentativas.extend([
        "gemini-1.5-flash",
        "gemini-2.0-flash-exp", 
        "gemini-1.5-pro"
    ])
    
    # Remove duplicatas mantendo ordem
    modelos_tentativas = list(dict.fromkeys(modelos_tentativas))
    
    print(f"Tentando {len(modelos_tentativas)} modelos...")
    
    for modelo_nome in modelos_tentativas:
        try:
            model = genai.GenerativeModel(model_name=modelo_nome)
            # Testa se o modelo realmente funciona fazendo uma chamada simples
            try:
                test_response = model.generate_content(
                    "Teste",
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=10
                    )
                )
                if test_response and test_response.text:
                    print(f"✓ Modelo Gemini disponível e funcional: {modelo_nome}")
                    _modelo_gemini_cache = model  # Cacheia o modelo válido
                    return model
            except Exception as test_error:
                error_msg = str(test_error)
                # Não imprime todos os erros 404 para evitar spam
                if "404" not in error_msg:
                    print(f"✗ Modelo {modelo_nome} criado mas não funcional: {error_msg[:80]}")
                continue
        except Exception as e:
            error_msg = str(e)
            if "404" not in error_msg:
                print(f"✗ Modelo {modelo_nome} não disponível: {error_msg[:80]}")
            continue
    
    print("⚠ Erro: Nenhum modelo Gemini disponível após testar todas as opções")
    return None


async def get_pontuacao_sugestao(text: str):
    """ Usa Google Gemini para sugerir pontuação """
    if not ENABLE_LLM:
        print("LLM desabilitado (ENABLE_LLM=false)")
        return None
    
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY não configurada")
        return None
    
    print(f"Chamando a API do Google Gemini (modelo: {GEMINI_MODEL})")
    
    prompt = f"""Você é um especialista em pontuação em português.
    Analise o texto e sugira onde adicionar vírgulas e pontos para melhorar a clareza.
    Responda APENAS com o texto corrigido, sem explicações ou comentários adicionais.

    Texto: {text}
    Correção:"""

    try: 
        model = obter_modelo_gemini()
        if model is None:
            return None
        
        # Configurações de geração
        generation_config = genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=500,
        )
        
        print("Enviando requisição para o Gemini...")
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        if response and response.text:
            return response.text.strip()
        
        return None
            
    except Exception as e:
        print(f"Erro ao chamar Gemini: {str(e)}")
        return None


async def enriquecer_match_com_ia(texto: str, match: Dict) -> Dict:
    """Enriquece cada erro encontrado pelo LanguageTool com explicações didáticas da IA"""
    if not ENABLE_LLM or not GEMINI_API_KEY:
        return match
    
    try:
        erro_texto = texto[match["offset"]:match["offset"] + match["length"]]
        contexto_antes = texto[max(0, match["offset"]-30):match["offset"]]
        contexto_depois = texto[match["offset"] + match["length"]:match["offset"] + match["length"] + 30]
        
        sugestoes = match.get("replacements", [])
        sugestoes_texto = ", ".join([s.get("value", s) if isinstance(s, dict) else str(s) for s in sugestoes[:3]])
        
        prompt = f"""Você é um professor de português especializado em redação.

        Erro encontrado: "{erro_texto}"
        Contexto: "{contexto_antes}[ERRO]{contexto_depois}"
        Mensagem do LanguageTool: {match["message"]}
        Sugestões de correção: {sugestoes_texto}

        Forneça uma explicação didática e curta (máximo 2 linhas) sobre este erro, explicando por que está errado e como corrigir.
        Responda APENAS com a explicação, sem formatação ou prefixos."""

        
        model = obter_modelo_gemini()
        if model is None:
            return match
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=150
            )
        )
        
        if response and response.text:
            match["ai_explanation"] = response.text.strip()
            
    except Exception as e:
        print(f"Erro ao enriquecer match com IA: {e}")
    
    return match


async def melhorar_sugestoes_com_ia(texto: str, match: Dict) -> Dict:
    """Usa IA para melhorar ou gerar sugestões quando LanguageTool tem poucas opções"""
    if not ENABLE_LLM or not GEMINI_API_KEY:
        return match
    
    
    sugestoes_existentes = match.get("replacements", [])
    if len(sugestoes_existentes) >= 3:
        return match
    
    try:
        erro_texto = texto[match["offset"]:match["offset"] + match["length"]]
        contexto_antes = texto[max(0, match["offset"]-30):match["offset"]]
        contexto_depois = texto[match["offset"] + match["length"]:match["offset"] + match["length"] + 30]
        
        prompt = f"""O texto contém um erro neste trecho:
        "{erro_texto}" no contexto: "{contexto_antes}[ERRO]{contexto_depois}"

        Erro detectado: {match["message"]}

        Sugira 3 alternativas de correção adequadas ao contexto de uma redação formal.
        Responda APENAS com uma lista JSON no formato: ["sugestão1", "sugestão2", "sugestão3"]"""

        # Tenta usar modelos alternativos se o padrão falhar
        model = obter_modelo_gemini()
        if model is None:
            return match
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.4,
                max_output_tokens=200
            )
        )
        
        if response and response.text:
            
            resposta_texto = response.text.strip()
            
            if "```json" in resposta_texto:
                resposta_texto = resposta_texto.split("```json")[1].split("```")[0].strip()
            elif "```" in resposta_texto:
                resposta_texto = resposta_texto.split("```")[1].split("```")[0].strip()
            
            try:
                sugestoes_ia = json.loads(resposta_texto)
                if isinstance(sugestoes_ia, list):
                    s
                    sugestoes_existentes_valores = [
                        s.get("value", s) if isinstance(s, dict) else str(s) 
                        for s in sugestoes_existentes
                    ]
                    todas_sugestoes = list(set(sugestoes_existentes_valores + sugestoes_ia))
                    
                    match["replacements"] = [{"value": s} for s in todas_sugestoes[:5]]
            except json.JSONDecodeError:
                print(f"Erro ao parsear JSON das sugestões: {resposta_texto}")
            
    except Exception as e:
        print(f"Erro ao melhorar sugestões com IA: {e}")
    
    return match


async def detectar_erros_acentuacao_com_ia(texto: str, matches_languagetool: List[Dict]) -> List[Dict]:
    """Usa IA para detectar erros de acentuação que o LanguageTool pode ter perdido"""
    if not ENABLE_LLM or not GEMINI_API_KEY:
        return []
    
    
    if len(matches_languagetool) > 5:
        return []
    
    try:
        prompt = f"""Você é um especialista em gramática portuguesa do Brasil.

        Analise este texto e identifique SOMENTE erros REAIS de acentuação (palavras que deveriam ter acento mas NÃO têm):

        Texto: "{texto}"

        IMPORTANTE:
        - NÃO marque palavras que já estão corretamente acentuadas
        - NÃO marque palavras que não precisam de acento
        - Identifique APENAS palavras sem acento que DEVERIAM ter acento
        - Exemplos CORRETOS: "porem" (deveria ser "porém"), "tambem" (deveria ser "também")
        - Exemplos INCORRETOS: "regiões" (já está correto), "nação" (já está correto)

        Responda APENAS com um JSON array válido (sem texto adicional, sem markdown, sem explicações):
        [
        {{
            "palavra": "palavra sem acento encontrada",
            "correcao": "palavra corrigida com acento",
            "mensagem": "explicação curta do erro"
        }}
        ]

        Se não houver erros REAIS de acentuação, retorne: []"""

        model = obter_modelo_gemini()
        if model is None:
            return []
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  
                max_output_tokens=400,
                #response_mime_type="application/json"  
            )
        )
        


        
        if response and response.text:
            resposta_texto = response.text.strip()
            
            
            if "```json" in resposta_texto:
                resposta_texto = resposta_texto.split("```json")[1].split("```")[0].strip()
            elif "```" in resposta_texto:
                resposta_texto = resposta_texto.split("```")[1].split("```")[0].strip()
            
            
            import re
            json_match = re.search(r'\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\]', resposta_texto, re.DOTALL)
            if json_match:
                resposta_texto = json_match.group(0)
            
            try:
                erros_ia = json.loads(resposta_texto)
                if isinstance(erros_ia, list) and len(erros_ia) > 0:
                    
                    erros_formatados = []
                    for erro in erros_ia:
                       
                        palavra_erro = erro.get("palavra", "").strip()
                        correcao = erro.get("correcao", "").strip()
                        
                        if not palavra_erro or not correcao:
                            continue
                        
                       
                        if palavra_erro.lower() == correcao.lower():
                            print(f"⚠ Ignorando falso positivo: '{palavra_erro}' já está correto (correção igual à palavra)")
                            continue
                        
                        
                        offset = texto.lower().find(palavra_erro.lower())
                        
                        if offset != -1:
                            
                            ja_detectado = any(
                                m.get("offset") == offset and m.get("length") == len(palavra_erro)
                                for m in matches_languagetool
                            )
                            
                            if not ja_detectado:
                                erros_formatados.append({
                                    "message": erro.get("mensagem", f"Erro de acentuação: '{palavra_erro}' deveria ser '{correcao}'"),
                                    "replacements": [{"value": correcao}],
                                    "offset": offset,
                                    "length": len(palavra_erro),
                                    "ruleId": "AI_ACCENT_CHECK",
                                    "context": {},
                                    "source": "IA"
                                })
                    
                    if erros_formatados:
                        print(f"✓ IA detectou {len(erros_formatados)} erro(s) de acentuação que o LanguageTool não encontrou")
                    return erros_formatados
            except json.JSONDecodeError:
                print(f"Erro ao parsear JSON da verificação de acentuação: {resposta_texto}")
        
        return []
    except Exception as e:
        print(f"Erro ao detectar erros de acentuação com IA: {e}")
        return []


async def analisar_redacao_completa(texto: str, matches: List[Dict]) -> Optional[Dict]:
    """Análise geral da redação usando IA - usado quando não há erros básicos"""
    if not ENABLE_LLM or not GEMINI_API_KEY:
        return None
    
    try:
        num_erros = len(matches)
        
        if num_erros == 0:
            prompt = f"""Analise esta redação e responda SOMENTE com JSON válido (sem texto adicional, sem markdown):

Texto: "{texto}"

Responda APENAS com este JSON (sem explicações, sem markdown, sem texto antes ou depois):
{{
    "nivel_estimado": "básico" ou "intermediário" ou "avançado",
    "coesao": "análise descritiva sobre a coesão textual",
    "coerencia": "análise descritiva sobre a coerência textual",
    "sugestoes_gerais": ["sugestão específica 1", "sugestão específica 2", "sugestão específica 3"],
    "pontos_fortes": ["ponto forte 1", "ponto forte 2"],
    "pontos_melhoria": ["melhoria 1", "melhoria 2"],
    "exemplos_melhoria": [
        {{
            "problema": "frase ou trecho problemático identificado",
            "sugestao": "versão melhorada da frase",
            "explicacao": "breve explicação do porquê da melhoria"
        }}
    ]
}}

IMPORTANTE: 
- "sugestoes_gerais" deve ser um ARRAY de strings, não texto livre
- "exemplos_melhoria" deve conter exemplos PRÁTICOS de como melhorar frases específicas do texto
- Para cada exemplo, inclua: a frase problemática original, a versão melhorada e uma explicação breve
- Responda APENAS o JSON, sem texto adicional"""
        else:
            
            erros_resumo = "\n".join([f"- {m['message']}" for m in matches[:3]])
            prompt = f"""Analise esta redação e responda SOMENTE com JSON válido (sem texto adicional, sem markdown):

Texto: "{texto}"
Erros encontrados: {num_erros}
Principais erros: {erros_resumo}

Responda APENAS com este JSON (sem explicações, sem markdown):
{{
    "nivel_estimado": "básico" ou "intermediário" ou "avançado",
    "coesao": "análise breve sobre coesão",
    "coerencia": "análise breve sobre coerência",
    "sugestoes_gerais": ["sugestão específica 1", "sugestão específica 2"],
    "mensagem": "Corrija os erros básicos para obter análise completa"
}}

IMPORTANTE: 
- "sugestoes_gerais" deve ser um ARRAY de strings, não texto livre
- Responda APENAS o JSON, sem texto adicional"""

        
        model = obter_modelo_gemini()
        if model is None:
            return None
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=800,
                response_mime_type="application/json"  # Força resposta em JSON
            )
        )
        
        if response and response.text:
            resposta_texto = response.text.strip()
            
            
            if "```json" in resposta_texto:
                resposta_texto = resposta_texto.split("```json")[1].split("```")[0].strip()
            elif "```" in resposta_texto:
                resposta_texto = resposta_texto.split("```")[1].split("```")[0].strip()
            
            
            import re
           
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', resposta_texto, re.DOTALL)
            if json_match:
                resposta_texto = json_match.group(0)
            else:
                
                json_match = re.search(r'\[[^\[]*(?:\{[^\}]*\}[^\[]*)*\]', resposta_texto, re.DOTALL)
                if json_match:
                    resposta_texto = json_match.group(0)
            
            try:
                resultado = json.loads(resposta_texto)
               
                if isinstance(resultado, dict):
                   
                    if "sugestoes_gerais" in resultado:
                        if isinstance(resultado["sugestoes_gerais"], str):
                           
                            sugestoes = resultado["sugestoes_gerais"]
                            
                            if "\n" in sugestoes:
                                resultado["sugestoes_gerais"] = [s.strip() for s in sugestoes.split("\n") if s.strip()]
                            elif ". " in sugestoes:
                                
                                resultado["sugestoes_gerais"] = [s.strip() + "." for s in sugestoes.split(". ") if s.strip()]
                            else:
                                
                                resultado["sugestoes_gerais"] = [sugestoes]
                        elif not isinstance(resultado["sugestoes_gerais"], list):
                            resultado["sugestoes_gerais"] = []
                    
                    
                    if "pontos_fortes" in resultado and not isinstance(resultado["pontos_fortes"], list):
                        if isinstance(resultado["pontos_fortes"], str):
                            resultado["pontos_fortes"] = [resultado["pontos_fortes"]]
                        else:
                            resultado["pontos_fortes"] = []
                    
                   
                    if "pontos_melhoria" in resultado and not isinstance(resultado["pontos_melhoria"], list):
                        if isinstance(resultado["pontos_melhoria"], str):
                            resultado["pontos_melhoria"] = [resultado["pontos_melhoria"]]
                        else:
                            resultado["pontos_melhoria"] = []
                    
                    #
                    if "exemplos_melhoria" in resultado and not isinstance(resultado["exemplos_melhoria"], list):
                        resultado["exemplos_melhoria"] = []
                    
                    return resultado
                else:
                    print(f"Resposta não é um objeto JSON válido: {type(resultado)}")
                    return None
            except json.JSONDecodeError as e:
                
                print(f"Erro ao parsear JSON da análise completa: {str(e)}")
                print(f"Resposta recebida: {resposta_texto[:300]}")
                return {
                    "análise_texto": resposta_texto[:500],
                    "erro_parse": True,
                    "mensagem": "Erro ao processar resposta da IA. A IA retornou texto em vez de JSON."
                }
        
        return None
            
    except Exception as e:
        print(f"Erro na análise completa: {e}")
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
    
    # Verificar Google Gemini (LLM)
    try:
        if not ENABLE_LLM:
            health_status["services"]["gemini"] = {"status": "disabled", "reason": "ENABLE_LLM=false"}
        elif not GEMINI_API_KEY:
            health_status["services"]["gemini"] = {
                "status": "unavailable",
                "error": "GEMINI_API_KEY não configurada",
                "suggestion": "Configure a variável de ambiente GEMINI_API_KEY"
            }
            health_status["status"] = "degraded"
        else:
            
            try:
                models = genai.list_models()
                health_status["services"]["gemini"] = {
                        "status": "connected",
                    "model_configured": GEMINI_MODEL,
                    "api_available": True
                }
            except Exception as e:
                health_status["services"]["gemini"] = {
                    "status": "degraded",
                    "error": str(e),
                    "model_configured": GEMINI_MODEL
        }
        health_status["status"] = "degraded"
    except Exception as e:
        health_status["services"]["gemini"] = {"status": "unavailable", "error": str(e)}
        health_status["status"] = "degraded"
    
    return health_status

@app.on_event("startup")
async def startup_event():
    """ 
    Esta função é executada quando a aplicação inicia.
    Cria cliente HTTP reutilizável e verifica conectividade com LanguageTool.
    """
    global http_client
    
    # Cria o cliente HTTP de forma incondicional para permitir conexões futuras
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(LANGUAGETOOL_TIMEOUT),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
    )
    
    print(f"Conectando ao servidor LanguageTool ({LANGUAGETOOL_URL})...")

    try:
        response = await http_client.get(f"{LANGUAGETOOL_URL}/v2/languages", timeout=5.0)
        if response.status_code == 200:
            print("✓ Conectado ao LanguageTool com sucesso.")
        else:
            print(f"⚠ LanguageTool respondeu com status {response.status_code}")
            
    except httpx.ConnectError:
        print(f"⚠ AVISO: Não foi possível conectar ao LanguageTool em {LANGUAGETOOL_URL} neste momento.")
        print(f"O serviço pode estar inicializando. Conexões futuras serão tentadas dinamicamente.")
    except Exception as e:
        print(f"⚠ AVISO: Falha no teste de conexão com o LanguageTool: {e}")

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
    """ Recebe o texto e verifica erros gramaticais usando LanguageTool (sem IA automática). """
    
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
        
       
        if ENABLE_LLM and GEMINI_API_KEY:
            erros_acentuacao = await detectar_erros_acentuacao_com_ia(request_data.text, formatted_matches)
            formatted_matches.extend(erros_acentuacao)
        
        num_erros = len(formatted_matches)
        
        

        return {
            "original_text": request_data.text,
            "corrections_found": num_erros,
            "matches": formatted_matches,
            "ai_enabled": ENABLE_LLM and bool(GEMINI_API_KEY),
            "ai_ready": num_erros == 0,  
            "suggestion": "Corrija os erros básicos e clique em 'Análise Completa com IA' para obter análise detalhada" if num_erros > 0 else None
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


@app.post("/v2/analyze")
async def analyze_with_ai(request_data: TextRequest):
    """Endpoint separado para análise completa com IA - acionado manualmente pelo usuário"""
    if not ENABLE_LLM or not GEMINI_API_KEY:
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
        
        if http_client is None:
            raise HTTPException(
                status_code=503,
                detail="LanguageTool não está disponível."
            )
        
        response = await http_client.post(
            f"{LANGUAGETOOL_URL}/v2/check",
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
        
       
        if ENABLE_LLM and GEMINI_API_KEY:
            erros_acentuacao = await detectar_erros_acentuacao_com_ia(request_data.text, formatted_matches)
            formatted_matches.extend(erros_acentuacao)
        
        num_erros = len(formatted_matches)
        
       
        print("Iniciando análise completa com IA...")
        ai_analysis = await analisar_redacao_completa(request_data.text, formatted_matches)
        llm_punctuation_suggestion = None
        
        
        if num_erros == 0:
            llm_punctuation_suggestion = await get_pontuacao_sugestao(request_data.text)
        
        return {
            "original_text": request_data.text,
            "corrections_found": num_erros,
            "matches": formatted_matches,
            "llm_punctuation_suggestion": llm_punctuation_suggestion,
            "ai_analysis": ai_analysis,
            "ai_used": bool(ai_analysis or llm_punctuation_suggestion),
            "ai_ready": num_erros == 0
        }
        
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout ao conectar ao LanguageTool.")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="LanguageTool offline.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

if __name__ == "__main__":
    print("Iniciando o servidor FastAPI... em http://0.0.0.0:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)