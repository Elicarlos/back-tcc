import json
from typing import Dict, List, Optional
import google.generativeai as genai
from core.config import settings

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

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
                    print(f"[OK] Modelo Gemini disponível e funcional: {modelo_nome}")
                    _modelo_gemini_cache = model  # Cacheia o modelo válido
                    return model
            except Exception as test_error:
                error_msg = str(test_error)
                if "404" not in error_msg:
                    print(f"[ERRO] Modelo {modelo_nome} criado mas não funcional: {error_msg[:80]}")
                continue
        except Exception as e:
            error_msg = str(e)
            if "404" not in error_msg:
                print(f"[ERRO] Modelo {modelo_nome} não disponível: {error_msg[:80]}")
            continue
    
    print("[AVISO] Erro: Nenhum modelo Gemini disponível após testar todas as opções")
    return None


async def get_pontuacao_sugestao(text: str):
    """ Usa Google Gemini para sugerir pontuação """
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return None
    
    prompt = f"""Você é um especialista em pontuação em português.
    Analise o texto e sugira onde adicionar vírgulas e pontos para melhorar a clareza.
    Responda APENAS com o texto corrigido, sem explicações ou comentários adicionais.

    Texto: {text}
    Correção:"""

    try: 
        model = obter_modelo_gemini()
        if model is None:
            return None
        
        generation_config = genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=500,
        )
        
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
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
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
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
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
                    sugestoes_existentes_valores = [
                        s.get("value", s) if isinstance(s, dict) else str(s) 
                        for s in sugestoes_existentes
                    ]
                    todas_sugestoes = list(set(sugestoes_existentes_valores + sugestoes_ia))
                    match["replacements"] = [{"value": s} for s in todas_sugestoes[:5]]
            except json.JSONDecodeError:
                pass
            
    except Exception as e:
        print(f"Erro ao melhorar sugestões com IA: {e}")
    
    return match


async def detectar_erros_acentuacao_com_ia(texto: str, matches_languagetool: List[Dict]) -> List[Dict]:
    """Usa IA para detectar erros de acentuação que o LanguageTool pode ter perdido"""
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
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
                    return erros_formatados
            except json.JSONDecodeError:
                pass
        
        return []
    except Exception as e:
        print(f"Erro ao detectar erros de acentuação com IA: {e}")
        return []


async def analisar_redacao_completa(texto: str, matches: List[Dict], tema: Optional[str] = None) -> Optional[Dict]:
    """Análise geral da redação usando IA - usado quando não há erros básicos"""
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
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
                response_mime_type="application/json"
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
                    
                    if "exemplos_melhoria" in resultado and not isinstance(resultado["exemplos_melhoria"], list):
                        resultado["exemplos_melhoria"] = []
                    
                    return resultado
                return None
            except json.JSONDecodeError as e:
                return {
                    "análise_texto": resposta_texto[:500],
                    "erro_parse": True,
                    "mensagem": "Erro ao processar resposta da IA. A IA retornou texto em vez de JSON."
                }
        
        return None
            
    except Exception as e:
        print(f"Erro na análise completa: {e}")
        return None


async def analisar_imagem_redacao(image_bytes: bytes, mime_type: str, tema: Optional[str] = None) -> Optional[Dict]:
    """Analisa a imagem manuscrita diretamente por visão computacional usando IA"""
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return None
    
    contexto_tema = f"\nTema da Proposta de Redação: \"{tema}\"" if tema else ""
    
    prompt = f"""Você é um corretor especialista do ENEM e tutor de redação em português do Brasil.
    Analise a imagem da redação manuscrita fornecida{contexto_tema}.
    
    Você deve realizar as seguintes etapas:
    1. Transcrever todo o texto legível da redação.
    2. Avaliar a redação com base nas 5 competências do ENEM (C1, C2, C3, C4, C5), dando uma nota de 0 a 200 para cada uma (múltiplos de 40).
    3. Fazer uma análise descritiva de Coesão e Coerência.
    4. Listar pontos fortes, pontos de melhoria e sugestões gerais.
    5. Identificar trechos específicos com problemas (erros gramaticais, ortografia, concordância, estrutura) e propor a correção com explicação didática.
    
    Responda APENAS com um objeto JSON válido no seguinte formato:
    {{
        "texto_transcrito": "O texto completo que foi transcrito do manuscrito da imagem",
        "nivel_estimado": "básico" ou "intermediário" ou "avançado",
        "pontuacao_estimada": {{
            "c1": 120,
            "c2": 160,
            "c3": 120,
            "c4": 120,
            "c5": 80,
            "total": 600
        }},
        "coesao": "análise descritiva sobre a coesão textual",
        "coerencia": "análise descritiva sobre a coerência textual",
        "sugestoes_gerais": ["sugestão 1", "sugestão 2"],
        "pontos_fortes": ["ponto forte 1", "ponto forte 2"],
        "pontos_melhoria": ["ponto de melhoria 1", "ponto de melhoria 2"],
        "exemplos_melhoria": [
            {{
                "problema": "trecho problemático identificado no manuscrito",
                "sugestao": "versão corrigida e melhorada do trecho",
                "explicacao": "explicação didática do erro e da correção"
            }}
        ]
    }}
    
    IMPORTANTE: 
    - Retorne APENAS o JSON. Não use blocos de código com markdown (```json).
    - Se a imagem não contiver uma redação legível, retorne um erro amigável no campo "erro".
    """
    
    try:
        model = obter_modelo_gemini()
        # Se for gemini-pro, forçar gemini-1.5-flash pois gemini-pro antigo não suporta imagem
        modelo_nome = "gemini-1.5-flash"
        if model and hasattr(model, "model_name") and "pro" in model.model_name and "1.5" not in model.model_name:
            model_vision = genai.GenerativeModel(model_name=modelo_nome)
        else:
            model_vision = model or genai.GenerativeModel(model_name=modelo_nome)

        contents = [
            prompt,
            {
                "mime_type": mime_type,
                "data": image_bytes
            }
        ]
        
        response = model_vision.generate_content(
            contents,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1500,
                response_mime_type="application/json"
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
            
            return json.loads(resposta_texto)
            
    except Exception as e:
        print(f"Erro na análise de imagem com IA: {e}")
        return None


async def analisar_redacao_completa_por_competencias(texto: str, tema: Optional[str], erros_languagetool: List[Dict]) -> Dict:
    """Orquestra a análise das 5 competências do ENEM de forma individualizada de maneira concorrente."""
    from services.competencies_service import (
        analisar_competencia_1,
        analisar_competencia_2,
        analisar_competencia_3,
        analisar_competencia_4,
        analisar_competencia_5
    )
    from services.validation_service import verificar_anulacao_total
    import asyncio

    try:
        # Validação prévia de anulação total (nota zero)
        validacao = await verificar_anulacao_total(texto, tema)
        if validacao.get("anulado"):
            motivo = validacao.get("motivo")
            justificativa = validacao.get("justificativa")
            return {
                "pontuacao_estimada": {
                    "c1": 0, "c2": 0, "c3": 0, "c4": 0, "c5": 0, "total": 0
                },
                "detalhes_competencias": {
                    "c1": {"nota": 0, "justificativa": f"Redação anulada por {motivo}: {justificativa}", "detalhes": {}},
                    "c2": {"nota": 0, "justificativa": f"Redação anulada por {motivo}: {justificativa}", "detalhes": {}},
                    "c3": {"nota": 0, "justificativa": f"Redação anulada por {motivo}: {justificativa}", "detalhes": {}},
                    "c4": {"nota": 0, "justificativa": f"Redação anulada por {motivo}: {justificativa}", "detalhes": {}},
                    "c5": {"nota": 0, "justificativa": f"Redação anulada por {motivo}: {justificativa}", "detalhes": {}}
                },
                "anulado": True,
                "motivo_anulacao": motivo,
                "justificativa_anulacao": justificativa
            }

        c1_task = analisar_competencia_1(texto, erros_languagetool)
        c2_task = analisar_competencia_2(texto, tema)
        c3_task = analisar_competencia_3(texto, tema)
        c4_task = analisar_competencia_4(texto)
        c5_task = analisar_competencia_5(texto)

        c1, c2, c3, c4, c5 = await asyncio.gather(c1_task, c2_task, c3_task, c4_task, c5_task)

        total = c1.get("nota", 0) + c2.get("nota", 0) + c3.get("nota", 0) + c4.get("nota", 0) + c5.get("nota", 0)

        return {
            "pontuacao_estimada": {
                "c1": c1.get("nota", 0),
                "c2": c2.get("nota", 0),
                "c3": c3.get("nota", 0),
                "c4": c4.get("nota", 0),
                "c5": c5.get("nota", 0),
                "total": total
            },
            "detalhes_competencias": {
                "c1": c1,
                "c2": c2,
                "c3": c3,
                "c4": c4,
                "c5": c5
            },
            "anulado": False
        }
    except Exception as e:
        print(f"Erro na análise completa por competências: {e}")
        return {
            "pontuacao_estimada": {
                "c1": 120, "c2": 120, "c3": 120, "c4": 120, "c5": 120, "total": 600
            },
            "erro": str(e)
        }


