import json
from typing import Dict, List, Optional
import google.generativeai as genai
from core.config import settings
from services.ai_service import obter_modelo_gemini

async def analisar_competencia_1(texto: str, erros_languagetool: List[Dict]) -> Dict:
    """
    Analisa a Competência I: Domínio da modalidade escrita formal da Língua Portuguesa.
    Analisa estrutura sintática e desvios gramaticais/ortográficos.
    Nota máxima (200): Estrutura sintática excelente (máx 1 falha) e no máximo 2 desvios.
    """
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return {"nota": 120, "justificativa": "Análise da Competência I indisponível.", "detalhes": {}}

    resumo_erros = "\n".join([f"- Erro: {err.get('message')} (Contexto: '{texto[err.get('offset'):err.get('offset')+err.get('length')]}')" for err in erros_languagetool[:15]])

    prompt = f"""Você é um corretor oficial do ENEM. Analise a Competência I do texto abaixo.
    
    Texto da Redação:
    "{texto}"

    Erros gramaticais preliminares detectados pelo sistema:
    {resumo_erros}

    Instruções de Avaliação da Competência I:
    1. Estrutura sintática: Analise como o participante constrói suas orações/períodos. Identifique falhas como truncamento (pontuar orações que deviam estar no mesmo período), justaposição (emendar orações sem pontuação) ou excesso/falta de palavras. Classifique como excelente, boa, regular ou deficiente.
    2. Desvios: Erros de convenção da escrita (ortografia, acentuação, hífen, maiúsculas/minúsculas), desvios gramaticais (concordância, regência, pontuação, crase, paralelismo), escolha de registro (marcas de oralidade/informalidade) e escolha de vocabulário (palavras imprecisas).
    3. Critério para Nota Máxima (200): Estrutura sintática excelente (no máximo uma falha de estrutura sintática) E no máximo 2 desvios gramaticais/ortográficos de natureza leve.
    4. Atribua uma das notas possíveis da grade do ENEM: 0, 40, 80, 120, 160 ou 200.

    Responda APENAS com um objeto JSON no seguinte formato:
    {{
        "nota": 160,
        "justificativa": "Justificativa clara detalhando as falhas de estrutura e os desvios encontrados no texto.",
        "detalhes": {{
            "estrutura_sintatica_nivel": "excelente" | "boa" | "regular" | "deficiente",
            "falhas_sintaticas": ["exemplo de truncamento ou justaposição no texto"],
            "desvios": ["exemplo de desvio encontrado no texto"]
        }}
    }}
    """

    try:
        model = obter_modelo_gemini()
        if model is None:
            return {"nota": 120, "justificativa": "Modelo Gemini não disponível.", "detalhes": {}}

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json"
            )
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"Erro ao analisar Competência I: {e}")
    
    return {"nota": 120, "justificativa": "Erro na execução da análise da Competência I.", "detalhes": {}}


async def analisar_competencia_2(texto: str, tema: Optional[str] = None) -> Dict:
    """
    Analisa a Competência II: Compreensão do tema, tipologia textual e repertório sociocultural.
    - Abordagem do Tema: discussão completa de todos os elementos da frase temática vs tangenciamento.
    - Tipologia Textual: dissertativo-argumentativo em prosa, presença de partes embrionárias, traços constantes de narração.
    - Repertório Sociocultural: legitimado (áreas do conhecimento científico/cultural e que extrapola textos motivadores), pertinente e de uso produtivo.
    """
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return {"nota": 120, "justificativa": "Análise da Competência II indisponível.", "detalhes": {}}

    contexto_tema = f"Tema da Proposta: \"{tema}\"" if tema else "Tema não especificado."

    prompt = f"""Você é um corretor oficial do ENEM. Analise a Competência II do texto abaixo.
    
    {contexto_tema}
    
    Texto da Redação:
    "{texto}"

    Instruções de Avaliação da Competência II:
    1. Abordagem do Tema: Verifique se todos os elementos da frase temática foram discutidos ou se houve tangenciamento (quando fala do assunto geral, mas esquece partes centrais).
    2. Tipologia Textual: Verifique se o texto é dissertativo-argumentativo em prosa, contendo introdução, desenvolvimento/argumentação e conclusão com proporções adequadas. Partes muito curtas são chamadas de "embrionárias" e penalizadas. Traços de narração constantes impedem notas altas.
    3. Repertório Sociocultural: Verifique informações externas (citações, dados históricos, livros, filmes, filosofia, etc.) trazidas. A nota alta exige que o repertório seja LEGITIMADO (respaldado em áreas do conhecimento científico/cultural e que extrapola os textos motivadores), PERTINENTE (relacionado ao tema) e com USO PRODUTIVO (vinculado à argumentação do participante).
    4. Atribua uma das notas possíveis da grade do ENEM: 0, 40, 80, 120, 160 ou 200.

    Responda APENAS com um objeto JSON no seguinte formato:
    {{
        "nota": 160,
        "justificativa": "Justificativa clara explicando a abordagem temática, a estrutura do texto dissertativo e a legitimação/produtividade do repertório utilizado.",
        "detalhes": {{
            "abordagem_tema": "completa" | "tangencial" | "nula",
            "tipologia_textual": "adequada" | "inadequada" | "presenca_narracao",
            "repertorios_socioculturais": [
                {{
                    "repertorio": "Citação/filme/dado citado",
                    "legitimado": true | false,
                    "pertinente": true | false,
                    "produtivo": true | false,
                    "explicacao": "Breve explicação sobre a pertinência e produtividade deste repertório."
                }}
            ]
        }}
    }}
    """

    try:
        model = obter_modelo_gemini()
        if model is None:
            return {"nota": 120, "justificativa": "Modelo Gemini não disponível.", "detalhes": {}}

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json"
            )
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"Erro ao analisar Competência II: {e}")
    
    return {"nota": 120, "justificativa": "Erro na execução da análise da Competência II.", "detalhes": {}}


async def analisar_competencia_3(texto: str, tema: Optional[str] = None) -> Dict:
    """
    Analisa a Competência III: Seleção, relação, organização e interpretação de informações (coerência).
    - Projeto de texto: planejamento prévio visível, tese clara na introdução desenvolvida ao longo do texto.
    - Desenvolvimento: fundamentação de fatos/opiniões de forma clara, sem deixar relações implícitas.
    """
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return {"nota": 120, "justificativa": "Análise da Competência III indisponível.", "detalhes": {}}

    contexto_tema = f"Tema da Proposta: \"{tema}\"" if tema else "Tema não especificado."

    prompt = f"""Você é um corretor oficial do ENEM. Analise a Competência III do texto abaixo.
    
    {contexto_tema}
    
    Texto da Redação:
    "{texto}"

    Instruções de Avaliação da Competência III:
    1. Projeto de texto: É o planejamento prévio que se percebe lendo a redação. Verifique se o texto tem uma direção clara, se os argumentos foram bem selecionados, hierarquizados estrategicamente e se cumprem o que foi prometido na introdução (tese).
    2. Desenvolvimento: Avalie o desdobramento e fundamentação das ideias e opiniões. Um bom desenvolvimento explica as ideias claramente, não deixando para o leitor a tarefa de adivinhar a relação entre os argumentos e o ponto de vista (evitando lacunas argumentativas).
    3. Regra de Nota Zero: A nota será zero caso o texto seja considerado apenas um aglomerado de palavras sem direção e que tangencia o tema.
    4. Atribua uma das notas possíveis da grade do ENEM: 0, 40, 80, 120, 160 ou 200.

    Responda APENAS com um objeto JSON no seguinte formato:
    {{
        "nota": 160,
        "justificativa": "Justificativa clara baseada no projeto de texto estratégico e no aprofundamento ou lacunas do desenvolvimento dos argumentos.",
        "detalhes": {{
            "projeto_texto": "estrategico" | "com_falhas" | "inexistente",
            "desenvolvimento": "excelente" | "bom" | "regular" | "lacunar"
        }}
    }}
    """

    try:
        model = obter_modelo_gemini()
        if model is None:
            return {"nota": 120, "justificativa": "Modelo Gemini não disponível.", "detalhes": {}}

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json"
            )
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"Erro ao analisar Competência III: {e}")
    
    return {"nota": 120, "justificativa": "Erro na execução da análise da Competência III.", "detalhes": {}}


async def analisar_competencia_4(texto: str) -> Dict:
    """
    Analisa a Competência IV: Conhecimento dos mecanismos linguísticos de argumentação (coesão).
    - Recursos coesivos: presença constante de operadores argumentativos interparágrafos (entre parágrafos) e intraparágrafos (dentro dos parágrafos).
    - Repetições e Inadequações: penaliza repetições excessivas de conectivos e usos inadequados (que alteram o sentido pretendido).
    - Monobloco: texto sem parágrafos (máximo nota baixa).
    """
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return {"nota": 120, "justificativa": "Análise da Competência IV indisponível.", "detalhes": {}}

    prompt = f"""Você é um corretor oficial do ENEM. Analise a Competência IV do texto abaixo.
    
    Texto da Redação:
    "{texto}"

    Instruções de Avaliação da Competência IV:
    1. Recursos coesivos: Presença constante de operadores argumentativos (conjunções, pronomes, preposições) tanto dentro dos parágrafos (intraparágrafos) quanto entre os parágrafos (interparágrafos).
    2. Repetições e Inadequações: Verifique se há repetições excessivas de conectivos próximos uns dos outros ou uso inadequado deles (ex: usar "portanto" em uma relação que exigiria "porém").
    3. Monobloco: Classifique se o texto foi escrito sem separação de parágrafos. Redações escritas em formato monobloco têm penalidade severa (não passam de nota baixa).
    4. Atribua uma das notas possíveis da grade do ENEM: 0, 40, 80, 120, 160 ou 200.

    Responda APENAS com um objeto JSON no seguinte formato:
    {{
        "nota": 160,
        "justificativa": "Justificativa clara focando na variedade de recursos coesivos inter e intraparágrafos, bem como repetições ou inadequações de conectivos.",
        "detalhes": {{
            "is_monobloco": true | false,
            "coesao_interparagrafos": "excelente" | "boa" | "regular" | "insuficiente",
            "coesao_intraparagrafos": "excelente" | "boa" | "regular" | "insuficiente",
            "repeticoes_excessivas": ["conectivos repetidos desnecessariamente no texto"],
            "inadequacoes": ["conectivos usados de forma inadequada"]
        }}
    }}
    """

    try:
        model = obter_modelo_gemini()
        if model is None:
            return {"nota": 120, "justificativa": "Modelo Gemini não disponível.", "detalhes": {}}

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json"
            )
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"Erro ao analisar Competência IV: {e}")
    
    return {"nota": 120, "justificativa": "Erro na execução da análise da Competência IV.", "detalhes": {}}


async def analisar_competencia_5(texto: str) -> Dict:
    """
    Analisa a Competência V: Proposta de intervenção e Direitos Humanos.
    - Direitos Humanos: Zera a Competência V se incitar tortura, morte, censura, ou negar direitos fundamentais.
    - 5 Elementos essenciais: Ação (o quê), Agente (quem), Modo/Meio (como), Efeito (para quê), Detalhamento (informação adicional de algum elemento).
    """
    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return {"nota": 120, "justificativa": "Análise da Competência V indisponível.", "detalhes": {}}

    prompt = f"""Você é um corretor oficial do ENEM. Analise a Competência V do texto abaixo.
    
    Texto da Redação:
    "{texto}"

    Instruções de Avaliação da Competência V:
    1. Regras para Nota Zero (0) na Competência V:
       A nota na Competência V deve ser obrigatoriamente 0 se:
       - O candidato não apresentar nenhuma proposta de intervenção.
       - A proposta for copiada integralmente dos textos motivadores.
       - A proposta elaborada não tiver nenhuma relação com o assunto/tema.
       - A intervenção sugerida desrespeitar de forma explícita e deliberada os Direitos Humanos (como incitar violência, tortura, agressão física, censura ou negar direitos fundamentais).
    2. Elementos da proposta (caso não se enquadre em Nota Zero):
       A nota é calculada contando a presença de 5 elementos essenciais na proposta mais completa do texto (cada elemento presente soma 40 pontos, totalizando até 200):
       - Ação: O que deve ser feito na prática.
       - Agente: Quem vai executar a ação (Governo, mídia, escolas, sociedade, etc.).
       - Modo/Meio: Como ou por meio de que a ação será realizada.
       - Efeito: Para quê a ação será feita (consequência ou objetivo).
       - Detalhamento: Informação adicional, justificativa ou especificação a um dos quatro elementos anteriores.
    3. Atribua uma das notas possíveis da grade do ENEM: 0, 40, 80, 120, 160 ou 200.

    Responda APENAS com um objeto JSON no seguinte formato:
    {{
        "nota": 160,
        "justificativa": "Justificativa detalhada sobre quais elementos foram encontrados na proposta de intervenção e a confirmação sobre o respeito aos direitos humanos.",
        "detalhes": {{
            "respeita_direitos_humanos": true | false,
            "elementos_presentes": {{
                "acao": {{
                    "presente": true | false,
                    "trecho": "Trecho que descreve a ação ou null"
                }},
                "agente": {{
                    "presente": true | false,
                    "trecho": "Trecho que descreve o agente ou null"
                }},
                "modo_meio": {{
                    "presente": true | false,
                    "trecho": "Trecho que descreve o modo/meio ou null"
                }},
                "efeito": {{
                    "presente": true | false,
                    "trecho": "Trecho que descreve o efeito ou null"
                }},
                "detalhamento": {{
                    "presente": true | false,
                    "trecho": "Trecho que descreve o detalhamento ou null"
                }}
            }}
        }}
    }}
    """

    try:
        model = obter_modelo_gemini()
        if model is None:
            return {"nota": 120, "justificativa": "Modelo Gemini não disponível.", "detalhes": {}}

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json"
            )
        )
        if response and response.text:
            return json.loads(response.text.strip())
    except Exception as e:
        print(f"Erro ao analisar Competência V: {e}")
    
    
    return {"nota": 120, "justificativa": "Erro na execução da análise da Competência V.", "detalhes": {}}
