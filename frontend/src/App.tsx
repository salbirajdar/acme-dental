import { useState, useEffect, useRef } from 'react';
import { ChatMessage, ChatInput, QuickActions, TypingIndicator } from './components';
import { sendChatMessage, checkHealth, generateThreadId } from './services/api';
import type { Message } from './types';
import './App.css';

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  content: `Welcome to Acme Dental! I'm your AI assistant, here to help you with appointments and answer any questions about our services.

How can I help you today?`,
  type: 'assistant',
  timestamp: new Date(),
};

function App() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [threadId] = useState(generateThreadId);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkHealth()
      .then(() => setIsConnected(true))
      .catch(() => setIsConnected(false));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const addMessage = (content: string, type: Message['type']) => {
    const message: Message = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      content,
      type,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, message]);
  };

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return;

    addMessage(content, 'user');
    setIsLoading(true);

    try {
      const response = await sendChatMessage({
        message: content,
        thread_id: threadId,
      });
      addMessage(response.response, 'assistant');
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'An unexpected error occurred';

      if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
        addMessage(
          'Unable to connect to the server. Please make sure the backend is running.',
          'error'
        );
        setIsConnected(false);
      } else {
        addMessage(`Sorry, something went wrong: ${errorMessage}`, 'error');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <span className="logo-icon">🦷</span>
          <div className="header-text">
            <h1>Acme Dental</h1>
            <p className="tagline">AI-Powered Receptionist</p>
          </div>
        </div>
        {isConnected !== null && (
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot"></span>
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
        )}
      </header>

      <main className="chat-container">
        <div className="messages">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          {isLoading && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        <QuickActions onAction={handleSendMessage} disabled={isLoading} />
        <ChatInput onSend={handleSendMessage} disabled={isLoading} />
      </main>

      <footer className="footer">
        <p>Acme Dental Clinic - Your smile is our priority</p>
      </footer>
    </div>
  );
}

export default App;
