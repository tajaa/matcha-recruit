import { useState, useEffect } from 'react';
import { provisioning } from '../../api/client';
import type { GoogleWorkspaceConnectionStatus } from '../../types';

export function useGoogleWorkspace() {
  const [googleWorkspaceStatus, setGoogleWorkspaceStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleWorkspaceStatusLoading, setGoogleWorkspaceStatusLoading] = useState(false);

  const fetchGoogleWorkspaceStatus = async () => {
    setGoogleWorkspaceStatusLoading(true);
    try {
      const status = await provisioning.getGoogleWorkspaceStatus();
      setGoogleWorkspaceStatus(status);
    } catch (err) {
      console.error('Failed to fetch Google Workspace provisioning status:', err);
      setGoogleWorkspaceStatus(null);
    } finally {
      setGoogleWorkspaceStatusLoading(false);
    }
  };

  useEffect(() => {
    fetchGoogleWorkspaceStatus();
  }, []);

  const normalizedGoogleDomain = (googleWorkspaceStatus?.domain || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase();

  const googleDomainAvailable = Boolean(
    normalizedGoogleDomain &&
      googleWorkspaceStatus?.connected &&
      googleWorkspaceStatus.status === 'connected'
  );

  const googleAutoProvisionBadge = () => {
    if (googleWorkspaceStatusLoading) {
      return {
        label: 'Loading',
        tone: 'bg-zinc-800 text-zinc-400 border-zinc-700',
      };
    }
    if (
      !googleWorkspaceStatus ||
      !googleWorkspaceStatus.connected ||
      googleWorkspaceStatus.status === 'disconnected'
    ) {
      return {
        label: 'Disconnected',
        tone: 'bg-zinc-800 text-zinc-400 border-zinc-700',
      };
    }
    if (
      googleWorkspaceStatus.status === 'error' ||
      googleWorkspaceStatus.status === 'needs_action'
    ) {
      return {
        label: 'Needs Attention',
        tone: 'bg-red-900/30 text-red-300 border-red-500/30',
      };
    }
    if (googleWorkspaceStatus.auto_provision_on_employee_create) {
      return {
        label: 'ON',
        tone: 'bg-emerald-900/30 text-emerald-300 border-emerald-500/30',
      };
    }
    return {
      label: 'OFF',
      tone: 'bg-amber-900/30 text-amber-300 border-amber-500/30',
    };
  };

  return {
    status: googleWorkspaceStatus,
    loading: googleWorkspaceStatusLoading,
    normalizedGoogleDomain,
    googleDomainAvailable,
    googleAutoProvisionBadge,
  };
}
