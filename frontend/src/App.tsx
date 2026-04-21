import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { motion, AnimatePresence } from 'framer-motion';
import './index.css';

interface ChatHistoryItem {
  role: 'user' | 'assistant';
  content: string;
  tool?: string;
}

function App() {
  const [messages, setMessages] = useState<ChatHistoryItem[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    // Initial greeting
    setMessages([
      {
        role: 'assistant',
        content: 'Hello! I am your AI assistant. I can help answer questions or pull data from GitHub and Confluence using my specialized tools. Try asking "what is the repo info for tudormunteanCS/Law-Agent?" or "search confluence for architecture".',
      }
    ]);
  }, []);

  const handleSend = async () => {
    const text = inputValue.trim();
    if (!text || isLoading) return;

    setInputValue('');
    setIsLoading(true);

    const userMessage: ChatHistoryItem = { role: 'user', content: text };
    setMessages(prev => [...prev, userMessage]);

    // Format history for the API
    const apiHistory = messages.filter(m => m.role === 'user' || m.role === 'assistant').map(m => ({
      role: m.role,
      content: m.content
    }));

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: apiHistory })
      });

      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }

      const data = await response.json();
      
      const assistantMessage: ChatHistoryItem = {
        role: 'assistant',
        content: data.response,
        tool: data.tool && data.tool !== 'llm' && data.tool !== 'helper' ? data.tool : undefined
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error(error);
      setMessages(prev => [
        ...prev, 
        { role: 'assistant', content: 'Sorry, I encountered an error communicating with the server. Please ensure the backend is running.' }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderMarkdown = (text: string) => {
    const rawMarkup = marked.parse(text, { async: false }) as string;
    const cleanMarkup = DOMPurify.sanitize(rawMarkup);
    return { __html: cleanMarkup };
  };

  return (
    <div className="app-container">
      <div className="header">
        <h1>MCP Agent</h1>
        <p>Intelligent integration with GitHub & Confluence</p>
      </div>

      <div className="chat-container">
        <div className="messages">
          <AnimatePresence initial={false}>
            {messages.map((msg, idx) => (
              <motion.div 
                key={idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`message-wrapper ${msg.role}`}
              >
                <div className="message-label">
                  {msg.role === 'user' ? (
                    <>You <User size={14} /></>
                  ) : (
                    <><Bot size={14} /> Agent</>
                  )}
                </div>
                <div 
                  className={`message-bubble markdown`} 
                  dangerouslySetInnerHTML={renderMarkdown(msg.content)}
                />
                {msg.tool && (
                  <div className="message-metadata">
                    Tool used: <code>{msg.tool}</code>
                  </div>
                )}
              </motion.div>
            ))}
            
            {isLoading && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="message-wrapper agent"
              >
                <div className="message-label">
                  <Bot size={14} /> Agent
                </div>
                <div className="message-bubble">
                  <div className="typing-indicator">
                    <div className="dot"></div>
                    <div className="dot"></div>
                    <div className="dot"></div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <div className="input-form">
            <div className="textarea-wrapper">
              <textarea 
                value={inputValue}
                onChange={e => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your project..."
                disabled={isLoading}
                rows={1}
                style={{ height: 'auto', minHeight: '48px' }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = 'auto';
                  target.style.height = Math.min(target.scrollHeight, 150) + 'px';
                }}
              />
            </div>
            <button 
              className="send-button"
              onClick={handleSend}
              disabled={!inputValue.trim() || isLoading}
            >
              {isLoading ? <Loader2 size={20} className="animate-spin" /> : <Send size={20} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
