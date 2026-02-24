import { useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { complianceAPI } from '../../api/compliance';

export interface ComplianceCheckMessage {
  type: string;
  status?: string;
  message?: string;
  location?: string;
  new?: number;
  updated?: number;
  alerts?: number;
}

export function useComplianceCheck(selectedLocationId: string | null, companyId: string | null, onComplete: () => void) {
  const queryClient = useQueryClient();
  const [checkInProgress, setCheckInProgress] = useState(false);
  const [checkMessages, setCheckMessages] = useState<ComplianceCheckMessage[]>([]);

  const runComplianceCheck = useCallback(async () => {
    if (!selectedLocationId) return;

    setCheckInProgress(true);
    setCheckMessages([]);

    try {
      const response = await complianceAPI.checkCompliance(selectedLocationId, companyId || undefined);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

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
            setCheckMessages((prev) => [...prev, event]);
          } catch {
            // skip malformed
          }
        }
      }

      if (selectedLocationId) {
        queryClient.invalidateQueries({ queryKey: ['compliance-requirements', selectedLocationId, companyId] });
      }
      if (companyId) {
        queryClient.invalidateQueries({ queryKey: ['compliance-alerts', companyId] });
        queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
      }
      queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
      onComplete();
    } catch (error) {
      console.error('Compliance check failed:', error);
      setCheckMessages((prev) => [...prev, { type: 'error', message: 'Failed to run compliance check' }]);
    } finally {
      setCheckInProgress(false);
    }
  }, [selectedLocationId, companyId, queryClient, onComplete]);

  return { checkInProgress, checkMessages, runComplianceCheck };
}
