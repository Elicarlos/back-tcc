import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';

// Registra um formato customizado para marcar erros (apenas uma vez, ANTES de criar instâncias)
let errorFormatRegistered = false;

if (!errorFormatRegistered) {
  const Inline = Quill.import('blots/inline');
  
  class ErrorBlot extends Inline {
    static blotName = 'error';
    static tagName = 'span';
    static className = 'ql-error';
    
    static create() {
      const node = super.create();
      node.setAttribute('class', 'ql-error');
      return node;
    }
    
    static formats() {
      return true;
    }
  }
  
  Quill.register(ErrorBlot, true);
  errorFormatRegistered = true;
}

const QuillEditor = forwardRef(function QuillEditor({ value, onChange, placeholder, errors }, ref) {
  const editorRef = useRef(null);
  const quillInstanceRef = useRef(null);
  const isUpdatingRef = useRef(false);

  // Expõe métodos para o componente pai
  useImperativeHandle(ref, () => ({
    replaceText: (offset, length, replacement) => {
      if (!quillInstanceRef.current) return;
      
      const quill = quillInstanceRef.current;
      isUpdatingRef.current = true;
      
      try {
        // Remove a formatação de erro primeiro
        quill.formatText(offset, length, 'error', false, 'api');
        
        // Substitui o texto
        quill.deleteText(offset, length, 'api');
        quill.insertText(offset, replacement, 'api');
        
        // Move o cursor para depois do texto substituído
        quill.setSelection(offset + replacement.length, 0, 'api');
        
        // Atualiza o estado
        const html = quill.root.innerHTML;
        const text = quill.getText();
        onChange(html, text);
      } catch (e) {
        console.error('Erro ao substituir texto:', e);
      } finally {
        isUpdatingRef.current = false;
      }
    }
  }));

  useEffect(() => {
    if (editorRef.current && !quillInstanceRef.current) {
      
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

      
      if (value) {
        quillInstanceRef.current.root.innerHTML = value;
      }

      
      quillInstanceRef.current.on('text-change', () => {        
        if (isUpdatingRef.current) {
          return;
        }
        
        const html = quillInstanceRef.current.root.innerHTML;
        const text = quillInstanceRef.current.getText();
       
        onChange(html, text);
      });
    }

    return () => {
      
    };
  }, []);

  
  useEffect(() => {    
    // Só atualiza o conteúdo se o valor vier de fora (prop inicial) e não estivermos atualizando
    // Não atualiza durante a digitação normal do usuário
    if (quillInstanceRef.current && 
        value && 
        !isUpdatingRef.current &&
        quillInstanceRef.current.getText().trim() === '' &&
        (!errors || errors.length === 0)) {
      // Só atualiza se o editor estiver vazio (inicialização)
      isUpdatingRef.current = true;
      const delta = quillInstanceRef.current.clipboard.convert(value || '');
      quillInstanceRef.current.setContents(delta, 'silent');
      isUpdatingRef.current = false;
    }
  }, [value]);

  
  useEffect(() => {
    if (!quillInstanceRef.current) {
      return;
    }

    // Aguarda um pouco para garantir que o editor está pronto
    const timeoutId = setTimeout(() => {
      if (!quillInstanceRef.current) return;

      const quill = quillInstanceRef.current;
      const text = quill.getText();
      
      if (!errors || errors.length === 0) {        
        // Remove todas as marcações de erro se não houver erros
        if (text.length > 0) {
          isUpdatingRef.current = true;
          quill.formatText(0, text.length, 'error', false);
          isUpdatingRef.current = false;
        }
        return;
      }

      isUpdatingRef.current = true;
      
      // Primeiro, remove todas as marcações de erro existentes
      if (text.length > 0) {
        quill.formatText(0, text.length, 'error', false);
      }

      // Depois, aplica as novas marcações usando seleção e format()
      const range = quill.getSelection(true);
      
      errors.forEach((match) => {
        const offset = match.offset || 0;
        const length = match.length || 0;
        
        if (offset >= 0 && offset + length <= text.length && length > 0) {
          try {
            // Seleciona o texto primeiro
            quill.setSelection(offset, length, 'api');
            
            // Aplica o formato na seleção atual
            quill.format('error', true, 'api');
          } catch (e) {
            console.error('Erro ao marcar texto:', e);
          }
        }
      });
      
      // Restaura a seleção original se houver
      if (range) {
        quill.setSelection(range.index, range.length, 'api');
      } else {
        quill.setSelection(null, 'api');
      }
      
      isUpdatingRef.current = false;
    }, 200); // Delay aumentado para garantir sincronização

    return () => clearTimeout(timeoutId);
  }, [errors]);

  return (
    <div className="quill-editor-wrapper">
      <div ref={editorRef} style={{ height: '700px' }} />
    </div>
  );
});

export default QuillEditor;
