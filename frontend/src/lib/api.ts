import type { Role } from '@/lib/roles';

/** Jedna pozycja podglądu nadawania nazw. `proponowana` puste = `problem` mówi dlaczego. */
export interface RenameProposal {
  file_id: number;
  filename: string;
  doc_type: string | null;
  proponowana: string | null;
  problem: string | null;
}

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

  /** Zmiana WŁASNYCH danych konta (strona Profil). Rola i status tu nie wchodzą. */
  updateProfile: (data: { username?: string; full_name?: string; email?: string; locale?: string }) =>
    apiRequest<any>('/api/auth/me', {
      method: 'PATCH',
      body: data,
      token: getAuthToken(),
    }),

  /** Zmiana własnego hasła — zawsze za potwierdzeniem aktualnym hasłem. */
  changePassword: (current_password: string, new_password: string) =>
    apiRequest<void>('/api/auth/me/password', {
      method: 'POST',
      body: { current_password, new_password },
      token: getAuthToken(),
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

/** Kolumny, po których backend potrafi posortować listę plików (`SORT_KEYS`). */
export type SortKey = 'name' | 'type' | 'size' | 'category' | 'date';
export type SortOrder = 'asc' | 'desc';

// File management endpoints
export const filesApi = {
  list: (params: { folder_id?: number; search?: string; status?: string; mime_type?: string; sort_by?: SortKey; order?: SortOrder; skip?: number; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.folder_id) query.append('folder_id', String(params.folder_id));
    if (params.search) query.append('search', params.search);
    if (params.status) query.append('status', params.status);
    if (params.mime_type) query.append('mime_type', params.mime_type);
    if (params.sort_by) query.append('sort_by', params.sort_by);
    if (params.order) query.append('order', params.order);
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
  // Podgląd nadania nazw z pól dokumentu — NIC nie zmienia.
  renamePreview: (fileIds: number[]) =>
    apiRequest<{ pozycje: RenameProposal[] }>('/api/files/rename-preview', {
      method: 'POST', body: { file_ids: fileIds }, token: getAuthToken(),
    }),
  // Wykonanie: nazwy z podglądu albo poprawione ręcznie przez administratora.
  rename: (items: { file_id: number; filename: string }[]) =>
    apiRequest<{
      zmienione: { file_id: number; z: string; na: string; na_dysku: boolean }[];
      pominiete: { file_id: number; powod: string }[];
    }>('/api/files/rename', { method: 'POST', body: { items }, token: getAuthToken() }),

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

// Słownik ról. Odczyt dla każdego zalogowanego (front potrzebuje etykiet),
// zmiany tylko dla administratora — pilnuje tego backend.
export const rolesApi = {
  list: () =>
    apiRequest<Role[]>('/api/roles', { method: 'GET', token: getAuthToken() }),
  create: (data: { name: string; copy_permissions_from?: string | null }) =>
    apiRequest<Role>('/api/roles', { method: 'POST', body: data, token: getAuthToken() }),
  rename: (code: string, name: string) =>
    apiRequest<Role>(`/api/roles/${encodeURIComponent(code)}`, {
      method: 'PATCH',
      body: { name },
      token: getAuthToken(),
    }),
  remove: (code: string, reassignTo?: string | null) =>
    apiRequest<{
      deleted: string;
      users_moved: number;
      moved_to: string | null;
      permissions_removed: number;
    }>(
      `/api/roles/${encodeURIComponent(code)}` +
        (reassignTo ? `?reassign_to=${encodeURIComponent(reassignTo)}` : ''),
      { method: 'DELETE', token: getAuthToken() }
    ),
};

// Dashboard stats endpoints
export const dashboardApi = {
  stats: (days = 30) =>
    apiRequest<any>(`/api/dashboard/stats?days=${days}`, {
      method: 'GET',
      token: getAuthToken(),
    }),
  /** Ostatnio dodane dokumenty — rzut oka na Dashboardzie, wg uprawnień użytkownika. */
  recentFiles: (limit = 5) =>
    apiRequest<any[]>(`/api/dashboard/recent-files?limit=${limit}`, {
      method: 'GET',
      token: getAuthToken(),
    }),
  // Dzienne liczniki (ostatnie N dni). Admin → całość; pozostali → pliki z dostępnych
  // folderów oraz własne zapytania w czacie.
  activity: (days = 30) =>
    apiRequest<{
      days: string[];
      parsed: number[];
      queries: number[];
      scope: 'all' | 'own';
    }>(`/api/dashboard/activity?days=${days}`, { method: 'GET', token: getAuthToken() }),
  // Rozbicie aktywności na użytkowników — endpoint tylko dla administratora (403 dla reszty)
  byUser: (days = 30) =>
    apiRequest<{
      days: number;
      users: { user_id: number; name: string; parsed: number; queries: number }[];
    }>(`/api/dashboard/by-user?days=${days}`, { method: 'GET', token: getAuthToken() }),
  /** Stan serwera pod panele „Status systemu" i „Miejsce w systemie" (tylko admin). */
  systemStatus: () =>
    apiRequest<SystemStatus>('/api/dashboard/system-status', { method: 'GET', token: getAuthToken() }),
};

export interface SystemStatus {
  aplikacja: {
    online: boolean;
    load: number | null;
    cores: number | null;
    load_percent: number | null;
    memory_used: number | null;
    memory_total: number | null;
  };
  baza: { online: boolean; ms: number | null };
  parser: {
    online: boolean;
    docling: boolean;
    model: boolean;
    running: number | null;
    waiting: number | null;
  };
  magazyn: {
    dostepny: boolean;
    total?: number;
    used?: number;
    free?: number;
    percent?: number;
    documents_bytes: number;
  };
}

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
  /** Zapis pojedynczego ustawienia. Backend waliduje każdy klucz osobno. */
  updateKey: (key: string, value: string | number) =>
    apiRequest<any>(`/api/settings/${key}`, {
      method: 'PUT',
      body: { [key]: value },
      token: getAuthToken(),
    }),
  /** Ikona aplikacji: PNG albo SVG, kwadratowa. Walidację robi backend. */
  uploadAppIcon: (plik: File) => {
    const dane = new FormData();
    dane.append('plik', plik);
    return apiRequest<{ app_icon: string }>('/api/settings/app-icon', {
      method: 'POST',
      body: dane,
      token: getAuthToken(),
    });
  },
  resetAppIcon: () =>
    apiRequest<{ app_icon: string }>('/api/settings/app-icon', {
      method: 'DELETE',
      token: getAuthToken(),
    }),
  // Lekki endpoint dla wszystkich zalogowanych: auto-wylogowanie + dozwolone rozszerzenia
  session: () =>
    apiRequest<{ idle_timeout_minutes: number; allowed_extensions: string[] }>('/api/settings/session', {
      method: 'GET',
      token: getAuthToken(),
    }),
};

/** Identyfikacja instancji — bez uwierzytelnienia, bo potrzebuje jej też ekran logowania. */
export const brandingApi = {
  get: () => apiRequest<{ nazwa: string; kolor_nazwy: string; ikona: string }>('/api/branding', { method: 'GET' }),
};

/** Zgłoszenia do wsparcia technicznego (ekran „Skontaktuj się"). */
export const contactApi = {
  send: (tresc: string) =>
    apiRequest<{ wyslano: boolean; do: string }>('/api/contact', {
      method: 'POST',
      body: { tresc },
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
  /** Wzorzec nazwy pliku dla tego typu, np. „{typ}-nr-{numer}-{data}". */
  name_pattern?: string | null;
  active: boolean;
  /** Materiał od dostawcy zewnętrznego, a nie dokument organizacji. */
  external?: boolean;
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
      // Pytanie bez jakiegokolwiek kryterium — rejestr nie zwraca wtedy nic,
      // bo wyszukiwanie bez warunków oddałoby całą bazę i udawało odpowiedź.
      no_criteria?: boolean;
      // Wśród warunków jest NIEPEWNE dopasowanie frazy (tytuł, temat) — przy zerze
      // wyników warto jeszcze poszukać w treści. Przy numerze, dacie i osobie nie:
      // tam zero wyników znaczy, że takich dokumentów nie ma.
      phrase_filter?: boolean;
      // Towarzyszy `no_criteria`: czy wypowiedź była ogólnikowa („pokaż wszystkie
      // dokumenty") — wtedy prosimy o doprecyzowanie. Gdy nazywa coś konkretnego,
      // szukamy w treści, zamiast odsyłać użytkownika z niczym.
      generic_query?: boolean;
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

/** Jedno nadpisanie tłumaczenia widziane przez ekran administratora. */
export interface TranslationMeta {
  value: string;
  /** `human` — ktoś wpisał; `machine` — przetłumaczył model i nikt jeszcze nie sprawdził. */
  source: 'human' | 'machine';
  updated_at: string | null;
}

/** Poprawki tłumaczeń. Katalogi z obrazu zna FRONT, backend trzyma same poprawki. */
export const translationsApi = {
  /** Nadpisania dla języka wraz z metryczką (administrator). */
  meta: (locale: string) =>
    apiRequest<Record<string, TranslationMeta>>(`/api/translations/${locale}/meta`, {
      token: getAuthToken(),
    }),

  /** Zapis poprawki. Pusta wartość kasuje wpis i przywraca tekst z katalogu. */
  save: (locale: string, key: string, value: string) =>
    apiRequest<any>('/api/translations', {
      method: 'PUT',
      body: { locale, key, value },
      token: getAuthToken(),
    }),

  /** Tłumaczenie maszynowe wskazanych napisów — pierwszy przebieg dla nowego języka. */
  auto: (locale: string, items: { key: string; source: string }[]) =>
    apiRequest<{ translated: Record<string, string>; failed: string[] }>('/api/translations/auto', {
      method: 'POST',
      body: { locale, items },
      token: getAuthToken(),
    }),
};
