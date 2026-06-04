const API_BASE = '';

export async function apiRequest<T>(
  endpoint: string,
  options: {
    method?: string;
    body?: any;
    token?: string;
  } = {}
): Promise<T> {
  const { method = 'GET', body, token } = options;

  const headers: Record<string, string> = {};

  // Don't set Content-Type for FormData - let browser set it with boundary
  if (!(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const fetchOptions: RequestInit = {
    method,
    headers,
    credentials: 'include',
  };

  if (body !== undefined && method !== 'GET' && method !== 'HEAD') {
    fetchOptions.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, fetchOptions);

  if (!response.ok) {
    const errorText = await response.text();
    let errorData: any = {};
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { detail: errorText };
    }
    throw new Error(errorData?.detail || `API Error: ${response.status}`);
  }

  if (response.status === 204) {
    return {} as T;
  }

  const data = await response.json();
  return data as T;
}

// Helper to get auth token from localStorage
function getAuthToken(): string | undefined {
  const token = localStorage.getItem('auth_token');
  return token || undefined;
}

// Version endpoint (no auth required)
export const versionApi = {
  get: () =>
    apiRequest<any>('/api/version', {
      method: 'GET',
    }),
};

// Auth endpoints
export const authApi = {
  login: (email: string, password: string) =>
    apiRequest<any>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
    }),

  me: (token: string) =>
    apiRequest<any>('/api/auth/me', {
      method: 'GET',
      token,
    }),
};

// User management endpoints (admin only)
export const usersApi = {
  list: (token: string, skip = 0, limit = 50) =>
    apiRequest<any[]>('/api/auth/users', {
      method: 'GET',
      token,
    }),

  get: (token: string, userId: number) =>
    apiRequest<any>(`/api/auth/users/${userId}`, {
      method: 'GET',
      token,
    }),

  create: (token: string, data: { email: string; username: string; password: string; full_name?: string; role: string }) =>
    apiRequest<any>('/api/auth/register', {
      method: 'POST',
      body: data,
      token,
    }),

  update: (token: string, userId: number, data: { email?: string; username?: string; full_name?: string; role?: string; is_active?: boolean }) =>
    apiRequest<any>(`/api/auth/users/${userId}`, {
      method: 'PUT',
      body: data,
      token,
    }),

  delete: (token: string, userId: number) =>
    apiRequest<any>(`/api/auth/users/${userId}`, {
      method: 'DELETE',
      token,
    }),

  checkExists: (token: string, username: string) =>
    apiRequest<any>(`/api/auth/users/check/${username}`, {
      method: 'GET',
      token,
    }),
};

// File management endpoints
export const filesApi = {
  list: (params: { folder_id?: number; search?: string; status?: string; mime_type?: string; skip?: number; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.folder_id) query.append('folder_id', String(params.folder_id));
    if (params.search) query.append('search', params.search);
    if (params.status) query.append('status', params.status);
    if (params.mime_type) query.append('mime_type', params.mime_type);
    if (params.skip) query.append('skip', String(params.skip));
    if (params.limit) query.append('limit', String(params.limit));
    return apiRequest<any[]>(`/api/files/?${query.toString()}`, { method: 'GET', token: getAuthToken() });
  },
  upload: (formData: FormData) =>
    apiRequest<any>('/api/files/upload', { method: 'POST', body: formData, token: getAuthToken() }),
  get: (fileId: number) =>
    apiRequest<any>(`/api/files/${fileId}`, { method: 'GET', token: getAuthToken() }),
  download: (fileId: number) => {
    return `/api/files/${fileId}/download`;
  },
  delete: (fileId: number) =>
    apiRequest<any>(`/api/files/${fileId}`, { method: 'DELETE', token: getAuthToken() }),
  categories: () =>
    apiRequest<any[]>('/api/files/categories', { method: 'GET', token: getAuthToken() }),
  folderFiles: (folderId: number) =>
    apiRequest<any[]>(`/api/files/folder/${folderId}/files`, { method: 'GET', token: getAuthToken() }),
};

// Folder management endpoints
export const foldersApi = {
  tree: () =>
    apiRequest<any[]>('/api/folders/tree', { method: 'GET', token: getAuthToken() }),
  list: (skip = 0, limit = 50) =>
    apiRequest<any[]>(`/api/folders/?skip=${skip}&limit=${limit}`, { method: 'GET', token: getAuthToken() }),
  get: (folderId: number) =>
    apiRequest<any>(`/api/folders/${folderId}`, { method: 'GET', token: getAuthToken() }),
  create: (data: { name: string; parent_id?: number }) =>
    apiRequest<any>('/api/folders/', {
      method: 'POST',
      body: data,
      token: getAuthToken(),
    }),
  delete: (folderId: number) =>
    apiRequest<any>(`/api/folders/${folderId}`, {
      method: 'DELETE',
      token: getAuthToken(),
    }),
  addPermission: (folderId: number, data: { role: string; access_level: string }) =>
    apiRequest<any>(`/api/folders/${folderId}/permissions`, {
      method: 'POST',
      body: data,
      token: getAuthToken(),
    }),
  listPermissions: (folderId: number) =>
    apiRequest<any[]>(`/api/folders/${folderId}/permissions`, {
      method: 'GET',
      token: getAuthToken(),
    }),
  deletePermission: (folderId: number, permId: number) =>
    apiRequest<any>(`/api/folders/${folderId}/permissions/${permId}`, {
      method: 'DELETE',
      token: getAuthToken(),
    }),
};

// Dashboard stats endpoints
export const dashboardApi = {
  stats: () =>
    apiRequest<any>('/api/dashboard/stats', {
      method: 'GET',
      token: getAuthToken(),
    }),
};