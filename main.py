from fastapi import FastAPI, HTTPException, Depends
from schemas import TextRequest
import uvicorn
import httpx
import os
import json
import asyncio
from typing import Optional, Dict, List
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import database
import models
import schemas


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
    allow_origins=["*"],
    allow_credentials=False,
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


async def analisar_redacao_completa(texto: str, matches: List[Dict], tema: Optional[str] = None) -> Optional[Dict]:
    """Análise geral da redação usando IA - usado quando não há erros básicos"""
    if not ENABLE_LLM or not GEMINI_API_KEY:
        return None
    
    try:
        num_erros = len(matches)
        contexto_tema = f"\nTema da Proposta de Redação: \"{tema}\"" if tema else ""
        
        if num_erros == 0:
            prompt = f"""Analise esta redação{contexto_tema} e responda SOMENTE com JSON válido (sem texto adicional, sem markdown):

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
            prompt = f"""Analise esta redação{contexto_tema} e responda SOMENTE com JSON válido (sem texto adicional, sem markdown):

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
    
    try:
        models.Base.metadata.create_all(bind=database.engine)
        print("✓ Tabelas do banco de dados criadas com sucesso.")
        
        # População automática de temas se a tabela estiver vazia
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
async def check_text(request_data: TextRequest, db: Session = Depends(database.get_db)):
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
        
        

        response_json = {
            "original_text": request_data.text,
            "corrections_found": num_erros,
            "matches": formatted_matches,
            "ai_enabled": ENABLE_LLM and bool(GEMINI_API_KEY),
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
async def analyze_with_ai(request_data: TextRequest, db: Session = Depends(database.get_db)):
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

# ==========================================
# PERSISTÊNCIA E INFRAESTRUTURA DE DADOS
# ==========================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def obter_hash_senha(password: str) -> str:
    return pwd_context.hash(password)

def verificar_senha(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# --- ROTAS DE AUTENTICAÇÃO ---

@app.post("/auth/register", response_model=schemas.UserResponse)
def register_user(user_in: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
    
    novo_usuario = models.User(
        name=user_in.name,
        email=user_in.email,
        password_hash=obter_hash_senha(user_in.password),
        role=user_in.role,
        school_id=user_in.school_id,
        classroom_id=user_in.classroom_id
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario

@app.post("/auth/login", response_model=schemas.UserResponse)
def login_user(login_in: schemas.UserLogin, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == login_in.email).first()
    if not user or not verificar_senha(login_in.password, user.password_hash):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos.")
    return user

# --- ROTAS DE ESCOLA ---

@app.post("/schools", response_model=schemas.SchoolResponse)
def create_school(school_in: schemas.SchoolCreate, db: Session = Depends(database.get_db)):
    nova_escola = models.School(name=school_in.name)
    db.add(nova_escola)
    db.commit()
    db.refresh(nova_escola)
    return nova_escola

@app.get("/schools", response_model=List[schemas.SchoolResponse])
def list_schools(db: Session = Depends(database.get_db)):
    return db.query(models.School).all()

# --- ROTAS DE TURMAS ---

@app.post("/classrooms", response_model=schemas.ClassroomResponse)
def create_classroom(classroom_in: schemas.ClassroomCreate, db: Session = Depends(database.get_db)):
    nova_turma = models.Classroom(
        name=classroom_in.name,
        school_id=classroom_in.school_id
    )
    db.add(nova_turma)
    db.commit()
    db.refresh(nova_turma)
    return nova_turma

@app.get("/classrooms", response_model=List[schemas.ClassroomResponse])
def list_classrooms(db: Session = Depends(database.get_db)):
    return db.query(models.Classroom).all()

@app.get("/classrooms/school/{school_id}", response_model=List[schemas.ClassroomResponse])
def list_classrooms_by_school(school_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Classroom).filter(models.Classroom.school_id == school_id).all()

# --- ROTAS DE ATIVIDADES ---

@app.post("/activities", response_model=schemas.ActivityResponse)
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

@app.get("/activities/classroom/{classroom_id}", response_model=List[schemas.ActivityResponse])
def list_activities_by_classroom(classroom_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Activity).filter(models.Activity.classroom_id == classroom_id).all()

# --- ROTAS DE REDAÇÕES ---

@app.post("/essays", response_model=schemas.EssayDetailResponse)
async def create_essay(essay_in: schemas.EssayCreate, db: Session = Depends(database.get_db)):
    student = db.query(models.User).filter(models.User.id == essay_in.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Estudante não encontrado.")
    
    # Realiza correção/análise se o JSON não estiver pré-calculado
    correction_data = None
    if essay_in.correction_json:
        try:
            correction_data = json.loads(essay_in.correction_json)
        except:
            pass
            
    if not correction_data:
        formatted_matches = []
        if http_client is not None:
            try:
                response = await http_client.post(
                    f"{LANGUAGETOOL_URL}/v2/check",
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
                
        if ENABLE_LLM and GEMINI_API_KEY:
            try:
                erros_acentuacao = await detectar_erros_acentuacao_com_ia(essay_in.text, formatted_matches)
                formatted_matches.extend(erros_acentuacao)
            except Exception as e:
                print(f"Erro em acentuação: {e}")

        num_erros = len(formatted_matches)
        
        ai_analysis = None
        if ENABLE_LLM and GEMINI_API_KEY:
            try:
                ai_analysis = await analisar_redacao_completa(essay_in.text, formatted_matches, essay_in.theme)
            except Exception as e:
                print(f"Erro IA: {e}")

        llm_punctuation_suggestion = None
        if num_erros == 0 and ENABLE_LLM and GEMINI_API_KEY:
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
            "ai_used": bool(ai_analysis or llm_punctuation_suggestion),
            "ai_ready": num_erros == 0
        }

    c1, c2, c3, c4, c5 = 120, 120, 120, 120, 120
    if correction_data and correction_data.get("ai_analysis") and isinstance(correction_data["ai_analysis"], dict):
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

@app.get("/essays/student/{student_id}", response_model=List[schemas.EssayResponse])
def list_essays_by_student(student_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Essay).filter(models.Essay.student_id == student_id).order_by(models.Essay.created_at.desc()).all()

@app.get("/essays/classroom/{classroom_id}", response_model=List[schemas.EssayResponse])
def list_essays_by_classroom(classroom_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.Essay).join(models.User, models.Essay.student_id == models.User.id).filter(models.User.classroom_id == classroom_id).order_by(models.Essay.created_at.desc()).all()

@app.get("/essays/{essay_id}", response_model=schemas.EssayDetailResponse)
def get_essay_detail(essay_id: int, db: Session = Depends(database.get_db)):
    essay = db.query(models.Essay).filter(models.Essay.id == essay_id).first()
    if not essay:
        raise HTTPException(status_code=404, detail="Redação não encontrada.")
    return essay

@app.patch("/essays/{essay_id}/notes", response_model=schemas.EssayDetailResponse)
def update_essay_notes(essay_id: int, notes_in: Dict[str, str], db: Session = Depends(database.get_db)):
    essay = db.query(models.Essay).filter(models.Essay.id == essay_id).first()
    if not essay:
        raise HTTPException(status_code=404, detail="Redação não encontrada.")
    
    essay.teacher_notes = notes_in.get("teacher_notes", "")
    db.commit()
    db.refresh(essay)
    return essay

@app.get("/themes", response_model=List[schemas.ThemeResponse])
def list_themes(db: Session = Depends(database.get_db)):
    return db.query(models.Theme).filter(models.Theme.active == True).order_by(models.Theme.source.desc(), models.Theme.created_at.desc()).all()

@app.post("/themes", response_model=schemas.ThemeResponse)
def create_theme(theme: schemas.ThemeCreate, db: Session = Depends(database.get_db)):
    existing = db.query(models.Theme).filter(models.Theme.title == theme.title).first()
    if existing:
        if not existing.active:
            existing.active = True
            existing.source = theme.source
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Este tema já está cadastrado.")
    
    db_theme = models.Theme(title=theme.title, source=theme.source)
    db.add(db_theme)
    db.commit()
    db.refresh(db_theme)
    return db_theme

@app.delete("/themes/{theme_id}")
def delete_theme(theme_id: int, db: Session = Depends(database.get_db)):
    db_theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not db_theme:
        raise HTTPException(status_code=404, detail="Tema não encontrado.")
    
    # Soft delete
    db_theme.active = False
    db.commit()
    return {"message": "Tema removido com sucesso."}

if __name__ == "__main__":
    print("Iniciando o servidor FastAPI... em http://0.0.0.0:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)