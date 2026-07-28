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
    // Wygasła/nieprawidłowa sesja: 401 dla żądania z tokenem → wyczyść sesję
    // i wróć do logowania (zamiast pokazywać puste ekrany funkcjonalne).
    // 401 z logowania nie ma tokenu → obsługiwane niżej jako błędne dane.
    if (response.status === 401 && token && typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      throw new Error('Sesja wygasła. Zaloguj się ponownie.');
    }
    const errorText = await response.text();
    let errorData: any = {};
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { detail: errorText };
    }
    // FastAPI: `detail` bywa stringiem (HTTPException) albo tablicą obiektów
    // (błędy walidacji 422). Zamień na czytelny komunikat, nie "[object Object]".
    const detail = errorData?.detail;
    let message: string;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((e: any) => (e?.msg ? `${e.msg}${e?.loc ? ` (${e.loc.join('.')})` : ''}` : JSON.stringify(e)))
        .join('; ');
    } else if (detail) {
      message = typeof detail === 'object' ? JSON.stringify(detail) : String(detail);
    } else {
      message = `API Error: ${response.status}`;
    }
    throw new Error(message);
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
  changelog: () =>
    apiRequest<{ entries: { version: string; date: string; title?: string; changes: string[] }[] }>(
      '/api/changelog',
      { method: 'GET' }
    ),
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

  /** Initial setup registration - creates first admin without auth */
  setup: (data: { email: string; username: string; password: string; full_name?: string }) =>
    apiRequest<any>('/api/auth/register-setup', {
      method: 'POST',
      body: data,
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

  update: (token: string, userId: number, data: { email?: string; username?: string; full_name?: string; role?: string; is_active?: boolean; password?: string }) =>
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
  // Przeniesienie plików (jeden lub wiele) do innego folderu.
  // Backend aktualizuje też metadata.folder_id w bazie wektorowej.
  move: (fileIds: number[], folderId: number | null) =>
    apiRequest<{ moved: number[]; skipped: { file_id: number; powod: string }[] }>(
      '/api/files/move',
      { method: 'POST', body: { file_ids: fileIds, folder_id: folderId }, token: getAuthToken() }
    ),
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
  // Zmiana nazwy (admin) — backend przebudowuje ścieżki całego poddrzewa
  rename: (folderId: number, name: string) =>
    apiRequest<any>(`/api/folders/${folderId}`, {
      method: 'PATCH',
      body: { name },
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
  effectivePermissions: (folderId: number) =>
    apiRequest<{ role: string; access_level: string }[]>(
      `/api/folders/${folderId}/effective-permissions`,
      { method: 'GET', token: getAuthToken() }
    ),
  accessOverview: () =>
    apiRequest<Record<string, { folder_id: number; name: string; path: string; access_level: string; source: string }[]>>(
      '/api/folders/access-overview',
      { method: 'GET', token: getAuthToken() }
    ),
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
  // Dzienne liczniki (ostatnie N dni). Admin → wszyscy, pozostali → własne dane.
  activity: (days = 30) =>
    apiRequest<{
      days: string[];
      parsed: number[];
      queries: number[];
      scope: 'all' | 'own';
    }>(`/api/dashboard/activity?days=${days}`, { method: 'GET', token: getAuthToken() }),
};

// Settings endpoints
export const settingsApi = {
  get: () =>
    apiRequest<any>('/api/settings/', {
      method: 'GET',
      token: getAuthToken(),
    }),
  update: (data: { n8n_webhook_url: string }) =>
    apiRequest<any>('/api/settings/n8n_webhook_url', {
      method: 'PUT',
      body: data,
      token: getAuthToken(),
    }),
  updateChatWebhook: (data: { chat_webhook_url: string }) =>
    apiRequest<any>('/api/settings/chat_webhook_url', {
      method: 'PUT',
      body: data,
      token: getAuthToken(),
    }),
  updateAllowedExtensions: (data: { allowed_extensions: string }) =>
    apiRequest<any>('/api/settings/allowed_extensions', {
      method: 'PUT',
      body: data,
      token: getAuthToken(),
    }),
  updateIdleTimeout: (data: { idle_timeout_minutes: number }) =>
    apiRequest<any>('/api/settings/idle_timeout_minutes', {
      method: 'PUT',
      body: data,
      token: getAuthToken(),
    }),
  // Lekki endpoint dla wszystkich zalogowanych: parametry sesji (auto-wylogowanie)
  session: () =>
    apiRequest<{ idle_timeout_minutes: number }>('/api/settings/session', {
      method: 'GET',
      token: getAuthToken(),
    }),
};

// Chat — pomocnicze (samo wysyłanie wiadomości leci strumieniowo w chat/page.tsx)
export const chatApi = {
  // Czy trwa parsowanie (dzieli model z czatem) — do komunikatu „chwila".
  parseActive: () =>
    apiRequest<{ active: boolean }>('/api/chat/parse-active', {
      method: 'GET',
      token: getAuthToken(),
    }),
};

// ==================== Rejestr schematów typów dokumentów (#7B-2) ====================
export interface DocTypeField {
  name: string;
  type: string; // string | number | date | enum:v1,v2,...
  hint?: string | null;
}

export interface DocTypeSchema {
  id?: number;
  slug: string;
  name: string;
  criteria?: string | null;
  fields: DocTypeField[];
  active: boolean;
}

// Wyszukiwanie po polach strukturalnych (#7B-2)
export interface DocSearchHit {
  id: number;
  filename: string;
  folder_id?: number | null;
  doc_type?: string | null;
  fields: Record<string, string>;
}

export interface DocSearchFilter {
  doc_type: string | null;
  filters: { field: string; op: string; value: string }[];
}

export const docSearchApi = {
  search: (body: {
    doc_type?: string | null;
    filters: { field: string; op: string; value: string }[];
    limit?: number;
  }) =>
    apiRequest<DocSearchHit[]>('/api/doc-search', {
      method: 'POST',
      body,
      token: getAuthToken(),
    }),
  // Pytanie po polsku → LLM zamienia na filtr → wyniki (+ rozpoznany filtr).
  // `unknown_type` = pytanie wskazało rodzaj dokumentu, którego nie ma w rejestrze.
  nl: (query: string) =>
    apiRequest<{
      filter: DocSearchFilter;
      hits: DocSearchHit[];
      unknown_type?: string;
      known_types?: string[];
    }>('/api/doc-search/nl', {
      method: 'POST',
      body: { query },
      token: getAuthToken(),
    }),
};

export const docSchemasApi = {
  list: (includeInactive = false) =>
    apiRequest<DocTypeSchema[]>(
      `/api/doc-schemas${includeInactive ? '?include_inactive=true' : ''}`,
      { method: 'GET', token: getAuthToken() }
    ),
  // Upsert po slugu (dodaje lub aktualizuje). Tylko admin.
  upsert: (data: DocTypeSchema) =>
    apiRequest<DocTypeSchema>('/api/doc-schemas', {
      method: 'POST',
      body: data,
      token: getAuthToken(),
    }),
  delete: (slug: string) =>
    apiRequest<any>(`/api/doc-schemas/${slug}`, {
      method: 'DELETE',
      token: getAuthToken(),
    }),
};