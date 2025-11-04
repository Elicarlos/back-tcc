import { useState, useEffect, useRef, useCallback } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'
import QuillEditor from './QuillEditor'

const API_URL = 'http://127.0.0.1:8000'

function App() {  
  const [text, setText] = useState('');
  const [htmlContent, setHtmlContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [ignoredErrors, setIgnoredErrors] = useState(new Set()); // IDs dos erros ignorados
  const ignoredErrorsRef = useRef(new Set()); // Ref para acessar valor atual sem causar re-render
  const debounceTimerRef = useRef(null);
  const editorRef = useRef(null);
  
  // Atualiza a ref sempre que o estado muda
  useEffect(() => {
    ignoredErrorsRef.current = ignoredErrors;
  }, [ignoredErrors]);

  const handleEditorChange = (html, plainText) => {
    setHtmlContent(html);
    setText(plainText); // Mantém o texto original para corresponder aos offsets
  };

  const handleAnalyzeWithAI = async () => {
    if (!text.trim()) {
      setError("Por favor, digite um texto para analisar.");
      return;
    }

    setAiLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/v2/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'accept': 'application/json',
        },
        body: JSON.stringify({ text: text })
      });

      if (!response.ok) {
        const erroData = await response.json();
        throw new Error(erroData.detail || "Erro ao analisar com IA.");
      }

      const data = await response.json();
      setAiAnalysis(data);
      // Atualiza também o resultado com os erros encontrados
      if (data.matches) {
        setResult({
          ...result,
          matches: data.matches,
          corrections_found: data.corrections_found
        });
      }

    } catch (error) {
      setError(error.message || 'Erro ao conectar a api');
      console.error('Erro:', error);
    } finally {
      setAiLoading(false);
    }
  };

  const handleIgnoreError = (matchIndex) => {
    if (!result || !result.matches) return;
    
    const match = result.matches[matchIndex];
    // Cria um ID único para o erro baseado em offset + length + message
    const errorId = `${match.offset}-${match.length}-${match.message}`;
    
    setIgnoredErrors(prev => {
      const newSet = new Set(prev);
      newSet.add(errorId);
      return newSet;
    });
  };

  const handleReplaceText = (matchIndex, replacementIndex) => {
    if (!result || !result.matches || matchIndex >= result.matches.length) return;
    
    const match = result.matches[matchIndex];
    const replacement = match.replacements[replacementIndex];
    
    if (!replacement || !editorRef.current) return;
    
    const replacementText = typeof replacement === 'string' 
      ? replacement 
      : replacement.value;
    
    // Substitui o texto usando o método do editor
    editorRef.current.replaceText(
      match.offset,
      match.length,
      replacementText
    );
    
    // Remove o erro específico da lista de ignorados se estava ignorado
    // Isso permite que o erro desapareça após a correção
    const errorId = `${match.offset}-${match.length}-${match.message}`;
    setIgnoredErrors(prev => {
      const newSet = new Set(prev);
      newSet.delete(errorId);
      return newSet;
    });
  };

  const checkText = useCallback(async () => {
    if (!text.trim()) {
      setError("Por favor, digite um texto para verificar.");
      setResult(null);
      setIgnoredErrors(new Set()); // Limpa quando texto está vazio
      return;
    }

    console.log('Iniciando verificação do texto:', text.substring(0, 50));  // Debug
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/v2/check`, {
        method: 'POST', 
        headers: {
          'Content-Type': 'application/json',
          'accept': 'application/json',
        },
        body: JSON.stringify({ text: text})
      });

      if (!response.ok) {
        const erroData = await response.json();
        throw new Error(erroData.detail || "Erro ao verificar o texto."); 
      }

      const data = await response.json();
      console.log('Dados recebidos da API:', data);  // Debug
      
      // Preserva erros ignorados que ainda existem na nova verificação
      // Usa a ref para acessar o valor atual sem causar re-renderizações
      const previousIgnoredIds = ignoredErrorsRef.current;
      const newMatches = data.matches || [];
      const preservedIgnored = new Set();
      
      // Verifica quais erros ignorados ainda existem na nova verificação
      // Compara por offset + length + message para garantir que é o mesmo erro
      newMatches.forEach((match) => {
        const errorId = `${match.offset}-${match.length}-${match.message}`;
        if (previousIgnoredIds.has(errorId)) {
          preservedIgnored.add(errorId);
        }
      });
      
      setResult(data);
      setAiEnabled(data.ai_enabled || false);
      setIgnoredErrors(preservedIgnored); // Mantém apenas os que ainda existem
      setAiAnalysis(null);

    } catch (error) {
      setError(error.message || 'Erro ao conectar a api');
      console.error('Erro:', error);
      // Em caso de erro, mantém os erros ignorados atuais
    } finally {
      setLoading(false);
    }
  }, [text]);

  // Validação automática após a digitação (com debounce)
  useEffect(() => {
    // Limpa o timer anterior se existir
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Se o texto estiver vazio, limpa os resultados
    if (!text.trim()) {
      setResult(null);
      setError(null);
      setIgnoredErrors(new Set());
      return;
    }

   
    debounceTimerRef.current = setTimeout(() => {
      checkText();
    }, 1000); 

   
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [text, checkText]);

  return (
    <div className='app-container'>

      <div className='content-wrapper'>
        <div className='input-section'>
          <QuillEditor 
            ref={editorRef}
            value={htmlContent}
            onChange={handleEditorChange}
            placeholder='Digite o texto que deseja verificar'
            errors={result?.matches?.filter((match, index) => {
              const errorId = `${match.offset}-${match.length}-${match.message}`;
              return !ignoredErrors.has(errorId);
            }) || []}
          />

          {loading && (
            <div className="loading-indicator">
              <p>Verificando...</p>
              {aiEnabled && (
                <p className="ai-processing">Processando com IA...</p>
              )}
            </div>
          )}

          {error && (
            <div className="error-message">
              <strong>Erro:</strong> {error}
            </div>
          )}
        </div>

        <div className='result-container'>
          {result ? (
            <div className="result-section">
              <h2>Resultado</h2>
              
              {/* Debug info - remover em produção */}
              
              
              {/* Indicador de status da IA */}
              {result.ai_enabled ? (
                <div className="ai-status-bar">
                  <span className="ai-indicator"></span>
                  {result.ai_ready ? (
                    <span>✓ Texto pronto para análise completa com IA</span>
                  ) : (
                    <span>Corrija os erros básicos para obter melhor análise com IA</span>
                  )}
                </div>
              ) : (
                <div className="ai-status-bar" style={{ background: '#fff3cd', borderColor: '#ffc107' }}>
                  <span></span>
                  <span style={{ fontSize: '0.85rem', color: '#856404' }}>
                    IA não habilitada. Configure GEMINI_API_KEY para usar recursos de IA.
                  </span>
                </div>
              )}
              
              {result.suggestion && (
                <div className="suggestion-box">
                  <strong>💡 Dica:</strong> {result.suggestion}
                </div>
              )}
              
              {/* Botão para análise com IA */}
              {result.ai_enabled && (
                <div className="ai-analysis-button-container">
                  <button 
                    className="ai-analysis-button"
                    onClick={handleAnalyzeWithAI}
                    disabled={aiLoading || !text.trim()}
                    title={result.ai_ready ? "Clique para obter análise completa com IA" : "Corrija os erros básicos primeiro para melhor análise"}
                  >
                    {aiLoading ? (
                      <>⏳ Analisando com IA...</>
                    ) : (
                      <>🤖 Análise Completa com IA</>
                    )}
                  </button>
                </div>
              )}
              
              <div className="result-stats">
                <p>
                  <strong>Erros encontrados:</strong> {result.corrections_found ?? 0}
                  {ignoredErrors.size > 0 && (
                    <span style={{ fontSize: '0.85rem', color: '#666', marginLeft: '0.5rem' }}>
                      ({ignoredErrors.size} ignorado{ignoredErrors.size > 1 ? 's' : ''})
                    </span>
                  )}
                </p>
              </div>

              {result.matches && result.matches.length > 0 ? (
                <div className="matches-section">
                  {result.matches
                    .map((match, index) => {
                      const errorId = `${match.offset}-${match.length}-${match.message}`;
                      return { match, originalIndex: index, errorId, isIgnored: ignoredErrors.has(errorId) };
                    })
                    .filter(({ isIgnored }) => !isIgnored)
                    .map(({ match, originalIndex }, displayIndex) => (
                      <div key={originalIndex} className="match-item">
                        <div className="match-header">
                          <div style={{ flex: 1 }}>
                            {match.source === "IA" && (
                              <div style={{ fontSize: '0.75rem', color: '#2196f3', marginBottom: '0.25rem' }}>
                                Detectado pela IA
                              </div>
                            )}
                            <p><strong>Erro {displayIndex + 1}:</strong> {match.message}</p>
                          </div>
                          <button
                            className="ignore-button"
                            onClick={() => handleIgnoreError(originalIndex)}
                            title="Ignorar este erro"
                          >
                            ✕ Ignorar
                          </button>
                        </div>
                        
                        {match.ai_explanation && (
                          <div className="ai-explanation">
                            <div className="ai-header">
                              <span className="ai-icon"></span>
                              <strong>Explicação da IA:</strong>
                            </div>
                            <p>{match.ai_explanation}</p>
                          </div>
                        )}
                      
                      {match.replacements && match.replacements.length > 0 && (
                        <div className="replacements">
                          <strong>Sugestões:</strong>
                          <ul>
                              {match.replacements.map((replacement, i) => {
                                const replacementText = typeof replacement === 'string' 
                                  ? replacement 
                                  : replacement.value;
                                return (
                                  <li 
                                    key={i}
                                    className="replacement-item"
                                    onClick={() => handleReplaceText(originalIndex, i)}
                                    title="Clique para substituir"
                                  >
                                    {replacementText}
                              </li>
                                );
                              })}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-errors">
                  <p>✓ Nenhum erro encontrado!</p>
                  {result.ai_analysis && (
                    <p style={{ fontSize: '0.85rem', marginTop: '0.5rem', color: '#666' }}>
                      A análise completa da redação está disponível abaixo.
                    </p>
                  )}
                </div>
              )}

              {/* Análise completa da redação com IA */}
              {aiAnalysis && aiAnalysis.ai_analysis && (
                <div className="ai-analysis-section">
                  <h3>Análise da Redação</h3>
                  
                  {aiAnalysis.ai_analysis.nivel_estimado && (
                    <div className="analysis-item">
                      <strong>Nível estimado:</strong>{' '}
                      <span className={`nivel-badge nivel-${aiAnalysis.ai_analysis.nivel_estimado}`}>
                        {aiAnalysis.ai_analysis.nivel_estimado}
                      </span>
                    </div>
                  )}
                  
                  {aiAnalysis.ai_analysis.coesao && (
                    <div className="analysis-item">
                      <strong>Coesão:</strong> {aiAnalysis.ai_analysis.coesao}
                    </div>
                  )}
                  
                  {aiAnalysis.ai_analysis.coerencia && (
                    <div className="analysis-item">
                      <strong>Coerência:</strong> {aiAnalysis.ai_analysis.coerencia}
                    </div>
                  )}
                  
                  {aiAnalysis.ai_analysis.pontos_fortes && aiAnalysis.ai_analysis.pontos_fortes.length > 0 && (
                    <div className="analysis-item">
                      <strong>Pontos fortes:</strong>
                      <ul>
                        {aiAnalysis.ai_analysis.pontos_fortes.map((ponto, i) => (
                          <li key={i}>{ponto}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {aiAnalysis.ai_analysis.pontos_melhoria && aiAnalysis.ai_analysis.pontos_melhoria.length > 0 && (
                    <div className="analysis-item">
                      <strong>🔧 Pontos de melhoria:</strong>
                      <ul>
                        {aiAnalysis.ai_analysis.pontos_melhoria.map((ponto, i) => (
                          <li key={i}>{ponto}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {aiAnalysis.ai_analysis.sugestoes_gerais && aiAnalysis.ai_analysis.sugestoes_gerais.length > 0 && (
                    <div className="analysis-item">
                      <strong>Sugestões gerais:</strong>
                      <ul>
                        {aiAnalysis.ai_analysis.sugestoes_gerais.map((sugestao, i) => (
                          <li key={i}>{sugestao}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {aiAnalysis.ai_analysis.erro_parse && aiAnalysis.ai_analysis.análise_texto && (
                    <div className="analysis-item">
                      <p>{aiAnalysis.ai_analysis.análise_texto}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-result">
              <p>Os resultados aparecerão aqui automaticamente enquanto você digita.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App;