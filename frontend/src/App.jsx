import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'

const API_URL = 'http://127.0.0.1:8000'

function App() {  
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const checkText = async () => {
    if (!text.trim()) {
      setError("Por favor, digite um texto para verificar.");
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
  }

  return (
    <div className='app-container'>
      

      <div className='content-wrapper'>
        <div className='input-section'>
          <textarea 
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='Digite o texto que deseja verificar'
            rows={12}
            className='text-input'
          />

          <button
            onClick={checkText}
            disabled={loading || !text.trim()}
            className='check-button'
          >
            {loading ? 'Verificando...' : 'Verificar Texto'}
          </button>

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
                            {match.replacements.map((replacement, i) => (
                              <li key={i}>
                                {typeof replacement === 'string' 
                                  ? replacement 
                                  : replacement.value}
                              </li>
                            ))}
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
              <p>Os resultados aparecerão aqui após verificar um texto.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App;