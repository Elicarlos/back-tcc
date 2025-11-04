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
  const debounceTimerRef = useRef(null);
  const editorRef = useRef(null);

  const handleEditorChange = (html, plainText) => {
    setHtmlContent(html);
    setText(plainText); // Mantém o texto original para corresponder aos offsets
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
  };

  const checkText = useCallback(async () => {
    if (!text.trim()) {
      setError("Por favor, digite um texto para verificar.");
      setResult(null);
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

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
      setResult(data);

    } catch (error) {
      setError(error.message || 'Erro ao conectar a api');
      console.error('Erro:', error);
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
            errors={result?.matches || []}
          />

          {loading && (
            <div className="loading-indicator">
              <p>Verificando...</p>
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
              
              <div className="result-stats">
                <p><strong>Erros:</strong> {result.corrections_found}</p>
              </div>

              {result.corrections_found > 0 ? (
                <div className="matches-section">
                  {result.matches.map((match, index) => (
                    <div key={index} className="match-item">
                      <p><strong>Erro {index + 1}:</strong> {match.message}</p>
                      
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
                                  onClick={() => handleReplaceText(index, i)}
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