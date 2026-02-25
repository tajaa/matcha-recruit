import { useState } from 'react';
import { getAccessToken } from '../../api/client';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export function useBulkUpload(onSuccess: () => void) {
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [sendInvitationsOnUpload, setSendInvitationsOnUpload] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownloadTemplate = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/bulk-upload/template`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to download template');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'employee_bulk_upload_template.csv';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download template');
    }
  };

  const handleBulkUpload = async () => {
    if (!uploadFile) return;

    setUploadLoading(true);
    setUploadResult(null);
    setError(null);

    try {
      const token = getAccessToken();
      const formData = new FormData();
      formData.append('file', uploadFile);

      const response = await fetch(
        `${API_BASE}/employees/bulk-upload?send_invitations=${sendInvitationsOnUpload}`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        }
      );

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to upload CSV');
      }

      const result = await response.json();
      setUploadResult(result);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload CSV');
    } finally {
      setUploadLoading(false);
    }
  };

  const handleFileSelect = (file: File | null) => {
    if (file && file.type === 'text/csv') {
      setUploadFile(file);
      setUploadResult(null);
      setError(null);
    } else if (file) {
      setError('Please select a CSV file');
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFileSelect(file);
  };

  return {
    showBulkUploadModal,
    setShowBulkUploadModal,
    uploadFile,
    setUploadFile,
    uploadLoading,
    uploadResult,
    sendInvitationsOnUpload,
    setSendInvitationsOnUpload,
    isDragging,
    error,
    handleDownloadTemplate,
    handleBulkUpload,
    handleFileSelect,
    handleDragOver,
    handleDragLeave,
    handleDrop,
  };
}
