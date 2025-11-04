import { useEffect, useRef } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';

function QuillEditor({ value, onChange, placeholder }) {
  const editorRef = useRef(null);
  const quillInstanceRef = useRef(null);

  useEffect(() => {
    if (editorRef.current && !quillInstanceRef.current) {
      // Inicializa o Quill
      quillInstanceRef.current = new Quill(editorRef.current, {
        theme: 'snow',
        placeholder: placeholder || 'Digite o texto que deseja verificar',
        modules: {
          toolbar: [
            [{ 'header': [1, 2, 3, false] }],
            ['bold', 'italic', 'underline', 'strike'],
            [{ 'list': 'ordered'}, { 'list': 'bullet' }],
            [{ 'align': [] }],
            ['link'],
            ['clean']
          ]
        }
      });

      // Define o conteúdo inicial
      if (value) {
        quillInstanceRef.current.root.innerHTML = value;
      }

      // Escuta mudanças no editor
      quillInstanceRef.current.on('text-change', () => {
        const html = quillInstanceRef.current.root.innerHTML;
        const text = quillInstanceRef.current.getText();
        // Chama onChange com texto HTML e texto puro
        onChange(html, text);
      });
    }

    return () => {
      // Cleanup se necessário
    };
  }, []);

  // Atualiza o conteúdo quando value muda externamente
  useEffect(() => {
    if (quillInstanceRef.current && value !== quillInstanceRef.current.root.innerHTML) {
      quillInstanceRef.current.root.innerHTML = value || '';
    }
  }, [value]);

  return (
    <div className="quill-editor-wrapper">
      <div ref={editorRef} style={{ height: '400px' }} />
    </div>
  );
}

export default QuillEditor;

