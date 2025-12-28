import { useState } from 'react';
import type { BulkImportResult } from '../types';
import { bulkImport, candidates } from '../api/client';
import { Button, Card, CardHeader, CardContent, FileUpload } from '../components';

type ImportType = 'companies' | 'positions' | 'candidates';

export function BulkImport() {
  const [activeTab, setActiveTab] = useState<ImportType>('candidates');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (files: File[]) => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);

      if (activeTab === 'candidates') {
        // Candidates use bulk upload endpoint that handles all files at once
        const importResult = await candidates.bulkUpload(files);
        setResult(importResult);
      } else {
        // Companies/positions process files one at a time
        const results: BulkImportResult[] = [];
        for (const file of files) {
          const importResult = activeTab === 'companies'
            ? await bulkImport.companies(file)
            : await bulkImport.positions(file);
          results.push(importResult);
        }

        // Combine all results into one
        const combinedResult: BulkImportResult = {
          success_count: results.reduce((sum, r) => sum + r.success_count, 0),
          error_count: results.reduce((sum, r) => sum + r.error_count, 0),
          errors: results.flatMap(r => r.errors),
          imported_ids: results.flatMap(r => r.imported_ids),
        };

        setResult(combinedResult);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadTemplate = () => {
    if (activeTab !== 'candidates') {
      window.open(bulkImport.downloadTemplate(activeTab), '_blank');
    }
  };

  const tabClass = (tab: ImportType) => `
    px-4 py-2 text-sm font-medium rounded-lg transition-colors
    ${activeTab === tab
      ? 'bg-matcha-500 text-zinc-950'
      : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300'
    }
  `;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Bulk Import</h1>
        <p className="text-zinc-400 mt-1">Import candidates, companies, and positions</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <button className={tabClass('candidates')} onClick={() => setActiveTab('candidates')}>
          Candidates
        </button>
        <button className={tabClass('companies')} onClick={() => setActiveTab('companies')}>
          Companies
        </button>
        <button className={tabClass('positions')} onClick={() => setActiveTab('positions')}>
          Positions
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Upload Section */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-zinc-100">
                Upload {activeTab === 'candidates' ? 'Resumes' : activeTab === 'companies' ? 'Companies' : 'Positions'}
              </h2>
              {activeTab !== 'candidates' && (
                <Button variant="secondary" size="sm" onClick={handleDownloadTemplate}>
                  Download Template
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <FileUpload
              accept={activeTab === 'candidates' ? '.pdf,.docx,.doc' : '.csv,.json,.pdf'}
              onUpload={handleUpload}
              disabled={loading}
              multiple
              allowFolder
              label={loading ? 'Importing...' : activeTab === 'candidates' ? 'Upload resumes' : `Upload ${activeTab} files`}
              description={activeTab === 'candidates'
                ? 'Drag and drop PDF or DOCX resumes, or select a folder'
                : 'Drag and drop files or folders, or use the buttons below'}
            />

            {/* Instructions */}
            <div className="mt-6 p-4 bg-zinc-900/50 rounded-lg border border-zinc-800">
              <h3 className="text-sm font-medium text-zinc-300 mb-2">Instructions</h3>
              {activeTab === 'candidates' ? (
                <div className="text-sm text-zinc-500 space-y-2">
                  <p>Upload resume files to add candidates to your talent pool.</p>
                  <p className="mt-3">Supported formats:</p>
                  <ul className="list-disc list-inside space-y-1">
                    <li><strong className="text-zinc-400">PDF</strong> - Most common resume format</li>
                    <li><strong className="text-zinc-400">DOCX</strong> - Microsoft Word documents</li>
                  </ul>
                  <p className="mt-3 text-zinc-400">
                    Each resume will be parsed using AI to extract:
                  </p>
                  <ul className="list-disc list-inside space-y-1 mt-2">
                    <li>Name, email, phone</li>
                    <li>Skills and experience</li>
                    <li>Education history</li>
                    <li>Work history</li>
                  </ul>
                  <p className="mt-3 text-white">
                    Tip: Select an entire folder to import many resumes at once.
                  </p>
                </div>
              ) : activeTab === 'companies' ? (
                <div className="text-sm text-zinc-500 space-y-2">
                  <p>CSV format:</p>
                  <code className="block p-2 bg-zinc-900 rounded text-xs text-zinc-400">
                    name,industry,size<br />
                    Acme Corp,Technology,startup
                  </code>
                  <p className="mt-3">Fields:</p>
                  <ul className="list-disc list-inside space-y-1">
                    <li><strong className="text-zinc-400">name</strong> (required): Company name</li>
                    <li><strong className="text-zinc-400">industry</strong>: e.g., Technology, Finance</li>
                    <li><strong className="text-zinc-400">size</strong>: startup, mid, or enterprise</li>
                  </ul>
                  <p className="mt-3 text-zinc-400">
                    PDF files should contain tabular data with headers in the first row.
                  </p>
                </div>
              ) : (
                <div className="text-sm text-zinc-500 space-y-2">
                  <p>CSV format:</p>
                  <code className="block p-2 bg-zinc-900 rounded text-xs text-zinc-400 overflow-x-auto">
                    company_name,title,salary_min,salary_max,...
                  </code>
                  <p className="mt-3">Key fields:</p>
                  <ul className="list-disc list-inside space-y-1">
                    <li><strong className="text-zinc-400">company_name</strong> (required): Must match existing company</li>
                    <li><strong className="text-zinc-400">title</strong> (required): Job title</li>
                    <li><strong className="text-zinc-400">required_skills</strong>: Comma-separated list</li>
                    <li><strong className="text-zinc-400">experience_level</strong>: entry, mid, senior, lead, executive</li>
                    <li><strong className="text-zinc-400">remote_policy</strong>: remote, hybrid, onsite</li>
                  </ul>
                  <p className="mt-3 text-amber-500">
                    Note: Companies must be imported first before positions.
                  </p>
                  <p className="mt-2 text-zinc-400">
                    PDF files should contain tabular data with headers in the first row.
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Results Section */}
        <Card>
          <CardHeader>
            <h2 className="text-lg font-semibold text-zinc-100">Import Results</h2>
          </CardHeader>
          <CardContent>
            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 mb-4">
                {error}
              </div>
            )}

            {result ? (
              <div className="space-y-4">
                {/* Summary */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
                    <p className="text-3xl font-bold text-white">{result.success_count}</p>
                    <p className="text-sm text-zinc-400">Imported</p>
                  </div>
                  <div className={`p-4 rounded-lg border ${
                    result.error_count > 0
                      ? 'bg-red-500/10 border-red-500/20'
                      : 'bg-zinc-800 border-zinc-700'
                  }`}>
                    <p className={`text-3xl font-bold ${result.error_count > 0 ? 'text-red-400' : 'text-zinc-400'}`}>
                      {result.error_count}
                    </p>
                    <p className="text-sm text-zinc-400">Errors</p>
                  </div>
                </div>

                {/* Errors List */}
                {result.errors.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-zinc-300 mb-2">Errors</h3>
                    <div className="max-h-64 overflow-y-auto space-y-2">
                      {result.errors.map((err, i) => (
                        <div
                          key={i}
                          className="p-3 bg-red-500/5 border border-red-500/10 rounded-lg"
                        >
                          <p className="text-sm text-red-400">
                            {/* Handle both row-based errors (companies/positions) and file-based errors (candidates) */}
                            <span className="font-medium">
                              {err.row ? `Row ${err.row}:` : err.file ? `${err.file}:` : ''}
                            </span>{' '}
                            {err.error}
                          </p>
                          {err.data && (
                            <pre className="mt-2 text-xs text-zinc-500 overflow-x-auto">
                              {JSON.stringify(err.data, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Success Message */}
                {result.success_count > 0 && result.error_count === 0 && (
                  <div className="p-4 bg-zinc-800 border border-zinc-700 rounded-lg">
                    <p className="text-white">
                      All {result.success_count} {activeTab === 'candidates' ? 'resumes' : activeTab} imported successfully!
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
                  <svg className="w-8 h-8 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <p className="text-zinc-500">Upload a file to see import results</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default BulkImport;
