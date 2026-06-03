'use client';

import { useState, useEffect, useCallback } from 'react';
import { filesApi, foldersApi } from '@/lib/api';
import { useAuth } from '@/lib/store';

interface File {
  id: number;
  filename: string;
  file_path: string;
  mime_type: string | null;
  size: number | null;
  folder_id: number | null;
  uploaded_by: number;
  status: string;
  created_at: string;
  updated_at: string;
  folder?: { id: number; name: string; path: string } | null;
  uploader?: { id: number; username: string; email: string } | null;
}

interface Folder {
  id: number;
  name: string;
  path: string;
  parent_id: number | null;
  children: Folder[];
}

type ViewMode = 'list' | 'grid';

function formatFileSize(bytes: number | null): string {
  if (bytes === null) return '-';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const icons: Record<string, string> = {
    pdf: '📕',
    docx: '📘',
    doc: '📘',
    xlsx: '📗',
    xls: '📗',
    pptx: '📙',
    ppt: '📙',
  };
  return icons[ext] || '📄';
}

function getFileColor(mimeType: string | null): string {
  if (!mimeType) return 'text-gray-500';
  if (mimeType.includes('pdf')) return 'text-red-600';
  if (mimeType.includes('word')) return 'text-blue-600';
  if (mimeType.includes('spreadsheet')) return 'text-green-600';
  if (mimeType.includes('presentation')) return 'text-orange-600';
  return 'text-gray-500';
}

export default function FilesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [files, setFiles] = useState<File[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [currentFolderId, setCurrentFolderId] = useState<number | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<{ id: number; name: string }[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Load folders tree
  const loadFolders = useCallback(async () => {
    try {
      const res = await foldersApi.tree();
      setFolders(res || []);
    } catch (err) {
      console.error('Failed to load folders:', err);
    }
  }, []);

  // Load files
  const loadFiles = useCallback(async (folderId: number | null = null) => {
    setLoading(true);
    try {
      const params: { folder_id?: number; search?: string } = {};
      if (folderId) params.folder_id = folderId;
      if (searchQuery) params.search = searchQuery;

      const res = await filesApi.list(params);
      setFiles(res || []);
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  // Navigate to folder
  const navigateToFolder = async (folder: Folder) => {
    setCurrentFolderId(folder.id);
    setBreadcrumbs(prev => [...prev, { id: folder.id, name: folder.name }]);

    // Load files in this folder
    setLoading(true);
    try {
      const res = await filesApi.list({ folder_id: folder.id });
      setFiles(res || []);
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setLoading(false);
    }
  };

  // Go up breadcrumb
  const navigateToBreadcrumb = async (index: number) => {
    const newBreadcrumbs = breadcrumbs.slice(0, index);
    setBreadcrumbs(newBreadcrumbs);

    const folderId = newBreadcrumbs.length > 0
      ? newBreadcrumbs[newBreadcrumbs.length - 1].id
      : null;
    setCurrentFolderId(folderId);

    if (folderId) {
      try {
        const res = await filesApi.list({ folder_id: folderId });
        setFiles(res || []);
      } catch (err) {
        console.error('Failed to load files:', err);
      }
    } else {
      loadFiles();
    }
  };

  // Navigate to root
  const navigateToRoot = async () => {
    setCurrentFolderId(null);
    setBreadcrumbs([]);
    loadFiles();
  };

  // Handle file upload
  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (currentFolderId) {
        formData.append('folder_id', String(currentFolderId));
      }

      await filesApi.upload(formData);

      setShowUploadModal(false);
      loadFiles(currentFolderId);
    } catch (err) {
      console.error('Upload failed:', err);
      alert('Upload nieudany. Sprawdź poprawność pliku.');
    } finally {
      setUploading(false);
    }
  };

  // Delete file
  const handleDelete = async (fileId: number) => {
    if (!confirm('Czy na pewno usunąć ten plik?')) return;

    try {
      await filesApi.delete(fileId);
      loadFiles(currentFolderId);
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Usunięcie nie powiodło się.');
    }
  };

  // Download file
  const handleDownload = async (file: File) => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      alert('Brak tokenu autoryzacji');
      return;
    }
    try {
      const response = await fetch(`/api/files/${file.id}/download`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error('Download failed');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Pobieranie pliku nie powiodło się.');
    }
  };

  // Search
  useEffect(() => {
    const timeout = setTimeout(() => {
      loadFiles(currentFolderId);
    }, 300);
    return () => clearTimeout(timeout);
  }, [searchQuery, currentFolderId, loadFiles]);

  // Initial load
  useEffect(() => {
    loadFolders();
    loadFiles();
  }, [loadFolders, loadFiles]);

  // Top folders (4 per row)
  const rootFolders = folders.filter(f => f.parent_id === null);

  // Children of current folder
  const currentFolderChildren = folders.filter(f => f.parent_id === currentFolderId);

  // Get folder name by ID
  const getFolderName = (folderId: number | null): string | null => {
    if (!folderId) return null;
    const folder = folders.find(f => f.id === folderId);
    return folder?.name || null;
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-2xl font-bold text-gray-800">Eksplorator plików</h1>
          {isAdmin && (
            <button
              onClick={() => setShowUploadModal(true)}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
              disabled={uploading}
            >
              {uploading ? 'Wczytywanie...' : '⬆️ Prześlij plik'}
            </button>
          )}
        </div>

        {/* Breadcrumbs */}
        <div className="flex items-center space-x-2 text-sm">
          <button
            onClick={navigateToRoot}
            className="text-blue-600 hover:underline"
          >
            🏠 Home
          </button>
          {breadcrumbs.map((crumb, index) => (
            <span key={index} className="flex items-center">
              <span className="text-gray-400 mx-2">/</span>
              <button
                onClick={() => navigateToBreadcrumb(index)}
                className="text-blue-600 hover:underline"
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Folders - Top row (4 per row) */}
        {(currentFolderId === null || currentFolderChildren.length > 0) && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-gray-700 mb-3">📁 Katalogi</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {(currentFolderId === null ? rootFolders : currentFolderChildren).map((folder) => (
                <button
                  key={folder.id}
                  onClick={() => navigateToFolder(folder)}
                  className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow hover:bg-blue-50 text-left"
                >
                  <div className="text-3xl mb-2">📁</div>
                  <div className="font-medium text-gray-800 truncate">{folder.name}</div>
                  <div className="text-xs text-gray-500">{folder.path}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Files section */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-700">📄 Pliki</h2>
            <div className="flex items-center space-x-2">
              {/* Search */}
              <input
                type="text"
                placeholder="Szukaj pliku..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="border border-gray-300 rounded-md px-3 py-1 text-sm w-48"
              />
              {/* View mode toggle */}
              <div className="flex border border-gray-300 rounded-md overflow-hidden">
                <button
                  onClick={() => setViewMode('list')}
                  className={`px-3 py-1 text-sm ${viewMode === 'list' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'}`}
                >
                  ☰ Lista
                </button>
                <button
                  onClick={() => setViewMode('grid')}
                  className={`px-3 py-1 text-sm ${viewMode === 'grid' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'}`}
                >
                  ⊞ Kafelki
                </button>
              </div>
            </div>
          </div>

          {/* List View */}
          {viewMode === 'list' && (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ikona</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nazwa</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rozmiar</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data dodania</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Akcje</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {files.map((file) => (
                    <tr
                      key={file.id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => setSelectedFile(file)}
                    >
                      <td className="px-4 py-3">
                        <span className="text-2xl">{getFileIcon(file.filename)}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-800">{file.filename}</div>
                        <div className="text-xs text-gray-500">{file.mime_type}</div>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {formatFileSize(file.size)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          file.status === 'Przetworzono'
                            ? 'bg-green-100 text-green-800'
                            : file.status === 'Błąd przetwarzania'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-yellow-100 text-yellow-800'
                        }`}>
                          {file.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {new Date(file.created_at).toLocaleDateString('pl-PL')}
                        {' '}
                        {new Date(file.created_at).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex space-x-2">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                            className="text-blue-600 hover:text-blue-800 text-sm"
                          >
                            ⬇️ Pobierz
                          </button>
                          {isAdmin && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDelete(file.id); }}
                              className="text-red-600 hover:text-red-800 text-sm"
                            >
                              🗑️ Usuń
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {files.length === 0 && !loading && (
                    <tr>
                      <td className="px-4 py-8 text-center text-gray-500" colSpan={6}>
                        Brak plików w tym katalogu
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              {loading && (
                <div className="px-4 py-8 text-center text-gray-500">
                  Ładowanie...
                </div>
              )}
            </div>
          )}

          {/* Grid View */}
          {viewMode === 'grid' && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {files.map((file) => (
                <div
                  key={file.id}
                  onClick={() => setSelectedFile(file)}
                  className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow cursor-pointer"
                >
                  <div className="text-4xl mb-3 text-center">
                    {getFileIcon(file.filename)}
                  </div>
                  <div className="font-medium text-gray-800 text-sm truncate" title={file.filename}>
                    {file.filename}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {formatFileSize(file.size)}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {new Date(file.created_at).toLocaleDateString('pl-PL')}
                  </div>
                  <div className="flex space-x-1 mt-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                      className="text-xs text-blue-600 hover:text-blue-800"
                    >
                      ⬇️
                    </button>
                    {isAdmin && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(file.id); }}
                        className="text-xs text-red-600 hover:text-red-800"
                      >
                        🗑️
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {files.length === 0 && !loading && (
                <div className="col-span-full text-center text-gray-500 py-8">
                  Brak plików w tym katalogu
                </div>
              )}
            </div>
          )}
          {loading && viewMode === 'grid' && (
            <div className="text-center text-gray-500 py-8">Ładowanie...</div>
          )}
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-bold text-gray-800 mb-4">Prześlij plik</h2>
            <p className="text-sm text-gray-600 mb-4">
              Dozwolone typy: PDF, DOCX, XLSX, PPTX (max 100MB)
            </p>
            <input
              type="file"
              accept=".pdf,.docx,.xlsx,.pptx"
              onChange={handleUpload}
              className="w-full border border-gray-300 rounded-md p-2"
              disabled={uploading}
            />
            <div className="flex justify-end space-x-2 mt-4">
              <button
                onClick={() => setShowUploadModal(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                disabled={uploading}
              >
                Anuluj
              </button>
            </div>
          </div>
        </div>
      )}

      {/* File Preview Modal */}
      {selectedFile && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                <span>{getFileIcon(selectedFile.filename)}</span>
                {selectedFile.filename}
              </h2>
              <button
                onClick={() => setSelectedFile(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>

            <dl className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <dt className="text-sm text-gray-500">Typ pliku</dt>
                <dd className="text-gray-800">{selectedFile.mime_type || 'Nieznany'}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Rozmiar</dt>
                <dd className="text-gray-800">{formatFileSize(selectedFile.size)}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Status</dt>
                <dd className="text-gray-800">{selectedFile.status}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Data dodania</dt>
                <dd className="text-gray-800">
                  {new Date(selectedFile.created_at).toLocaleString('pl-PL')}
                </dd>
              </div>
              {selectedFile.folder && (
                <div>
                  <dt className="text-sm text-gray-500">Katalog</dt>
                  <dd className="text-gray-800">{selectedFile.folder.name}</dd>
                </div>
              )}
              {selectedFile.uploader && (
                <div>
                  <dt className="text-sm text-gray-500">Wczytał</dt>
                  <dd className="text-gray-800">{selectedFile.uploader.username}</dd>
                </div>
              )}
            </dl>

            <div className="flex space-x-2">
              <button
                onClick={() => handleDownload(selectedFile)}
                className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
              >
                ⬇️ Pobierz plik
              </button>
              {selectedFile.mime_type === 'application/pdf' && (
                <button
                  onClick={async () => {
                    const token = localStorage.getItem('auth_token');
                    if (!token) return;
                    try {
                      const response = await fetch(`/api/files/${selectedFile.id}/download`, {
                        headers: { 'Authorization': `Bearer ${token}` },
                      });
                      if (!response.ok) throw new Error('Preview failed');
                      const blob = await response.blob();
                      const url = URL.createObjectURL(blob);
                      window.open(url, '_blank');
                    } catch (e) {
                      alert('Podgląd nie powiódł się');
                    }
                  }}
                  className="flex-1 bg-gray-100 text-gray-800 px-4 py-2 rounded-md hover:bg-gray-200"
                >
                  👁️ Podgląd PDF
                </button>
              )}
              {isAdmin && (
                <button
                  onClick={() => { handleDelete(selectedFile.id); setSelectedFile(null); }}
                  className="flex-1 bg-red-100 text-red-800 px-4 py-2 rounded-md hover:bg-red-200"
                >
                  🗑️ Usuń
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}