type SocketState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed';

interface SocketMessage {
  type: string;
  payload?: Record<string, unknown>;
}

export type ConversationSocketHandler = (message: SocketMessage) => void;
export type ConversationSocketStateHandler = (state: SocketState) => void;

const DEFAULT_WS_PATH = '/ws/conversations';

function resolveWsBaseUrl(): string {
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
  const url = new URL(apiBase);
  const scheme = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${url.host}`;
}

export class ConversationWebSocketClient {
  private socket: WebSocket | null = null;
  private state: SocketState = 'idle';
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private queue: SocketMessage[] = [];
  private readonly onMessage: ConversationSocketHandler;
  private readonly onStateChange?: ConversationSocketStateHandler;

  constructor(
    onMessage: ConversationSocketHandler,
    onStateChange?: ConversationSocketStateHandler,
  ) {
    this.onMessage = onMessage;
    this.onStateChange = onStateChange;
  }

  connect(conversationId: number): void {
    this.clearTimers();
    this.updateState(this.state === 'connected' ? 'connected' : 'connecting');
    const wsBase = resolveWsBaseUrl();
    const clientId = `web-${Date.now()}`;
    const url = `${wsBase}${DEFAULT_WS_PATH}/${conversationId}?client_id=${clientId}`;
    this.socket = new WebSocket(url);
    this.socket.onopen = () => {
      this.updateState('connected');
      this.flushQueue();
      this.startHeartbeat();
    };
    this.socket.onmessage = event => {
      try {
        const parsed = JSON.parse(String(event.data)) as SocketMessage;
        this.onMessage(parsed);
      } catch {
        this.onMessage({ type: 'session.error', payload: { message: 'Invalid websocket payload' } });
      }
    };
    this.socket.onerror = () => {
      this.updateState('reconnecting');
    };
    this.socket.onclose = () => {
      this.clearTimers();
      if (this.state !== 'closed') {
        this.scheduleReconnect(conversationId);
      }
    };
  }

  send(message: SocketMessage): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
      return;
    }
    this.queue.push(message);
  }

  close(): void {
    this.updateState('closed');
    this.clearTimers();
    if (this.socket) {
      this.socket.close(1000, 'client close');
      this.socket = null;
    }
  }

  private flushQueue(): void {
    while (this.queue.length > 0 && this.socket && this.socket.readyState === WebSocket.OPEN) {
      const next = this.queue.shift();
      if (next) {
        this.socket.send(JSON.stringify(next));
      }
    }
  }

  private startHeartbeat(): void {
    this.heartbeatTimer = window.setInterval(() => {
      this.send({ type: 'session.heartbeat', payload: {} });
    }, 30_000);
  }

  private scheduleReconnect(conversationId: number): void {
    this.updateState('reconnecting');
    this.reconnectTimer = window.setTimeout(() => {
      this.connect(conversationId);
    }, 1500);
  }

  private clearTimers(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private updateState(next: SocketState): void {
    this.state = next;
    this.onStateChange?.(next);
  }
}
