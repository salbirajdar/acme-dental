import type { Message } from '../types';
import './ChatMessage.css';

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatContent(content: string): string {
  // Convert **text** to bold
  let formatted = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // Convert URLs to links
  formatted = formatted.replace(
    /(https?:\/\/[^\s]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  );

  // Convert newlines to breaks
  formatted = formatted.replace(/\n/g, '<br>');

  return formatted;
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  return (
    <div className={`message ${message.type}`}>
      <div
        className={`message-content ${isStreaming ? 'streaming' : ''}`}
        dangerouslySetInnerHTML={{ __html: formatContent(message.content) }}
      />
      <span className="message-time">{formatTime(message.timestamp)}</span>
    </div>
  );
}
