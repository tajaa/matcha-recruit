import { useState, useCallback, useRef } from 'react';
import { getAccessToken } from '../../api/client';
import type { ERSimilarCasesAnalysis } from '../../types';

export interface SimilarCasesStreamMessage {
  type: 'phase' | 'cached' | 'complete' | 'error';
  step?: string;
  message: string;
  timestamp: string;
  done?: boolean;
}

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export function useERSimilarCasesStream() {
  const [streaming, setStreaming] = useState(false);
  const [messages, setMessages] = useState<SimilarCasesStreamMessage[]>([]);
  const [result, setResult] = useState<ERSimilarCasesAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setStreaming(false);
    setMessages([]);
    setResult(null);
    setError(null);
  }, []);

  const runAnalysis = useCallback(async (caseId: string) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    setStreaming(true);
    setMessages([]);
    setResult(null);
    setError(null);

    const token = getAccessToken();

    try {
      const response = await fetch(
        `${API_BASE}/er/cases/${caseId}/analysis/similar-cases`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        const text = await response.text();
        let detail = 'Analysis failed';
        try {
          detail = JSON.parse(text).detail || detail;
        } catch {
          // ignore
        }
        setError(detail);
        setMessages((prev) => [
          ...prev,
          { type: 'error', message: detail, timestamp: new Date().toISOString() },
        ]);
        setStreaming(false);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setError('No response body');
        setStreaming(false);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;

          const payload = trimmed.slice(6);
          if (payload === '[DONE]') continue;

          try {
            const event = JSON.parse(payload);
            const now = new Date().toISOString();

            if (event.type === 'phase') {
              setMessages((prev) => {
                const updated = prev.map((m) =>
                  m.type === 'phase' && !m.done ? { ...m, done: true } : m,
                );
                return [...updated, { ...event, timestamp: now }];
              });
            } else if (event.type === 'cached') {
              setMessages((prev) => {
                const updated = prev.map((m) =>
                  m.type === 'phase' && !m.done ? { ...m, done: true } : m,
                );
                return [...updated, { type: 'cached' as const, message: event.message, timestamp: now, done: true }];
              });
              if (event.result) {
                setResult(event.result);
              }
            } else if (event.type === 'complete') {
              setMessages((prev) => {
                const updated = prev.map((m) =>
                  !m.done ? { ...m, done: true } : m,
                );
                return [...updated, { type: 'complete' as const, message: 'Analysis complete', timestamp: now, done: true }];
              });
              if (event.result) {
                setResult(event.result);
              }
            } else if (event.type === 'error') {
              setError(event.message);
              setMessages((prev) => [
                ...prev,
                { type: 'error' as const, message: event.message, timestamp: now, done: true },
              ]);
            }
          } catch {
            // skip malformed
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        const msg = err instanceof Error ? err.message : 'Stream failed';
        setError(msg);
        setMessages((prev) => [
          ...prev,
          { type: 'error', message: msg, timestamp: new Date().toISOString(), done: true },
        ]);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, []);

  return { streaming, messages, result, error, runAnalysis, reset };
}
