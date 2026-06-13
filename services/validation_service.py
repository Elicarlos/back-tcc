import json
from typing import Dict, Optional
from core.config import settings
from services.ai_service import executar_chamada_gemini_com_retry

async def verificar_anulacao_total(texto: str, tema: Optional[str] = None) -> Dict:
    """
    Verifica se a redação deve ser anulada (nota zero total) de acordo com as regras do ENEM:
    - Fuga ao tema
    - Não atendimento ao tipo textual (dissertativo-argumentativo)
    - Texto insuficiente (até 7 linhas)
    - Parte deliberadamente desconectada
    """
    # Verificação rápida heurística de tamanho para evitar chamadas de LLM em textos vazios ou curtíssimos
    palavras = [p for p in texto.split() if p.strip()]
    if len(palavras) <= 15:
        return {
            "anulado": True,
            "motivo": "texto_insuficiente",
            "justificativa": f"O texto é insuficiente por apresentar extensão extremamente reduzida ({len(palavras)} palavras), o que equivale a menos de 7 linhas escritas."
        }

    if not settings.ENABLE_LLM or not settings.GEMINI_API_KEY:
        return {"anulado": False, "motivo": "nenhum", "justificativa": ""}

    contexto_tema = f"Tema da Proposta: \"{tema}\"" if tema else "Tema não especificado."

    prompt = f"""Você é um avaliador oficial de redações do ENEM.
    Analise o texto abaixo e determine se ele comete alguma infração que resulte em anulação total (nota zero) de acordo com os critérios do ENEM.

    {contexto_tema}

    Texto da Redação:
    "{texto}"

    Critérios de Anulação (Nota Zero Total):
    1. Fuga ao tema: Quando o texto não aborda o tema proposto, nem mesmo o assunto mais geral da prova.
    2. Não atendimento ao tipo textual: Quando o texto foge da estrutura dissertativo-argumentativa em prosa (por exemplo: é um poema, uma narrativa pura, uma carta, uma receita, etc.).
    3. Texto insuficiente: Redação com até 7 linhas escritas (considere que uma linha padrão de redação manuscrita possui de 7 a 10 palavras. Se o texto total estimado for menor ou igual a 7 linhas, marque como insuficiente).
    4. Parte deliberadamente desconectada: Quando o texto apresenta trechos propositais que não têm relação alguma com o tema ou com a argumentação, inseridos como deboche, protesto, mensagens pessoais, receitas, hinos, etc.

    Responda APENAS com um objeto JSON no formato abaixo, sem comentários adicionais:
    {{
        "anulado": true | false,
        "motivo": "fuga_tema" | "tipo_textual" | "texto_insuficiente" | "partes_desconectadas" | "nenhum",
        "justificativa": "Explicação detalhada da infração cometida ou justificativa de por que o texto é válido."
    }}
    """

    try:
        response_text = await executar_chamada_gemini_com_retry(
            prompt,
            temperature=0.1,
            max_tokens=300,
            response_mime_type="application/json"
        )
        
        if response_text:
            resultado = json.loads(response_text.strip())
            return {
                "anulado": bool(resultado.get("anulado", False)),
                "motivo": resultado.get("motivo", "nenhum"),
                "justificativa": resultado.get("justificativa", "")
            }
    except Exception as e:
        print(f"Erro ao verificar anulação da redação: {e}")
        
    return {"anulado": False, "motivo": "nenhum", "justificativa": ""}
