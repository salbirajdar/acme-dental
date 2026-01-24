export type MessageType = 'user' | 'assistant' | 'error';

export interface Message {
  id: string;
  content: string;
  type: MessageType;
  timestamp: Date;
}

export interface ChatRequest {
  message: string;
  thread_id: string;
}

export interface ChatResponse {
  response: string;
  thread_id: string;
}

export interface HealthResponse {
  status: string;
  cache_stats: Record<string, unknown> | null;
}
