'use client';

import { useState, useEffect, useCallback, useMemo, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { docSchemasApi, filesApi, foldersApi, settingsApi } from '@/lib/api';
import { RenameDialog } from '@/components/rename-dialog';
import { useAuth } from '@/lib/store';
import { czasLokalny, dataLokalna, godzinaLokalna } from '@/lib/czas';
import { ROLE_ADMIN, isAdmin as czyAdmin, roleLabel, useRoles } from '@/lib/roles';

interface File {
  id: number;
  filename: string;
  file_path: string;
  mime_type: string | null;
  size: number | null;
  folder_id: number | null;
  uploaded_by: number;
  status: string;
  doc_type?: string | null;
  original_filename?: string | null;
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
  can_write?: boolean;
  file_count?: number;
  children?: Folder[];
}

// Spłaszcz drzewo folderów do płaskiej listy (zachowując pola węzłów).
// Dzięki temu filtrowanie po parent_id działa dla podfolderów na każdym poziomie
// (drzewo z backendu ma dzieci zagnieżdżone, nie na płasko).
function flattenFolderTree(nodes: Folder[]): Folder[] {
  const out: Folder[] = [];
  const walk = (list: Folder[]) => {
    for (const n of list) {
      out.push(n);
      if (n.children?.length) walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

// Wyszukanie folderu po id w płaskiej liście
function findFolder(list: Folder[], id: number | null): Folder | null {
  if (id === null) return null;
  return list.find((f) => f.id === id) ?? null;
}

type ViewMode = 'list' | 'grid';

const ACCESS_LABELS: Record<string, string> = {
  read: 'Odczyt',
  write: 'Zapis',
};
// Ranga poziomu dostępu: brak < odczyt < zapis
const accessRank = (lvl?: string): number => (lvl === 'write' ? 2 : lvl === 'read' ? 1 : 0);

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

function FilesPageInner() {
  const { user } = useAuth();
  const isAdmin = czyAdmin(user);
  // Role przypisywalne do folderów. Administrator ma pełny dostęp z definicji,
  // więc nadawanie mu uprawnień nic by nie zmieniło.
  const { roles } = useRoles();
  const assignableRoles = useMemo(
    () => roles.filter((r) => r.code !== ROLE_ADMIN).map((r) => ({ value: r.code, label: r.name })),
    [roles],
  );
  const searchParams = useSearchParams();
  const deepLinkDone = useRef(false); // deep-link ?folder=<id> stosujemy raz
  const [files, setFiles] = useState<File[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [currentFolderId, setCurrentFolderId] = useState<number | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<{ id: number; name: string }[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Postęp wgrywania wielu plików (jeden POST na plik, sekwencyjnie)
  const [uploadItems, setUploadItems] = useState<
    { name: string; status: 'pending' | 'uploading' | 'done' | 'error'; error?: string }[]
  >([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  
  // Folder creation
  const [showCreateFolderModal, setShowCreateFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [folderCreating, setFolderCreating] = useState(false);
  // Role, które nowy podfolder odziedziczy po folderze nadrzędnym (informacyjnie)
  const [inheritedPerms, setInheritedPerms] = useState<
    { role: string; access_level: string }[]
  >([]);

  // Zarządzanie uprawnieniami folderu (RBAC po roli)
  const [permFolder, setPermFolder] = useState<Folder | null>(null);
  const [permissions, setPermissions] = useState<
    { id: number; role: string; access_level: string }[]
  >([]);
  // Efektywne uprawnienia = własne + odziedziczone po folderach nadrzędnych
  const [permEffective, setPermEffective] = useState<
    { role: string; access_level: string }[]
  >([]);
  // Uprawnienia odziedziczone (efektywne folderu nadrzędnego) — do rozróżnienia
  // co jest własnym rozszerzeniem, a co dziedziczonym minimum
  const [permInherited, setPermInherited] = useState<
    { role: string; access_level: string }[]
  >([]);
  const [permLoading, setPermLoading] = useState(false);
  // Zmiana nazwy folderu (admin)
  const [renameFolder, setRenameFolder] = useState<Folder | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renaming, setRenaming] = useState(false);
  // Zaznaczanie i przenoszenie plików
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  // Słownik kategorii: kolumna KATEGORIA i okno nadawania nazw pokazują nazwę
  // czytelną („Zarządzenie"), a nie slug z rejestru („zarzadzenie").
  const [kategorie, setKategorie] = useState<Record<string, string>>({});
  const [oknoAkcji, setOknoAkcji] = useState(false);
  const [komunikat, setKomunikat] = useState('');
  const [renameTarget, setRenameTarget] = useState<number[] | null>(null);
  const [moveTarget, setMoveTarget] = useState<number[] | null>(null);  // pliki do przeniesienia
  const [moveFolderId, setMoveFolderId] = useState<string>('');
  // Rozszerzenia z ustawień administratora — okno wysyłki musi pokazywać to samo,
  // co realnie przepuszcza backend. Wartość startowa służy tylko do czasu odpowiedzi.
  const [allowedExts, setAllowedExts] = useState<string[]>(['pdf', 'docx', 'xlsx']);
  const [moving, setMoving] = useState(false);
  // Pusty początek: właściwą rolę ustawia efekt, gdy dojedzie słownik ról.
  const [newPermRole, setNewPermRole] = useState('');
  const [newPermAccess, setNewPermAccess] = useState('read');

  // Load folders tree
  const loadFolders = useCallback(async () => {
    try {
      const res = await foldersApi.tree();
      setFolders(flattenFolderTree(res || []));
    } catch (err) {
      console.error('Failed to load folders:', err);
    }
  }, []);

  // Load files
  // UWAGA na domyślną wartość: musi być BIEŻĄCY folder, nie root. Wołania bez
  // argumentu (po usunięciu, przeniesieniu, wgraniu pliku) ładowały wcześniej
  // katalog główny, przez co widok przeskakiwał na root.
  const loadFiles = useCallback(async (folderId: number | null = currentFolderId) => {
    setLoading(true);
    try {
      // limit: backend domyślnie oddaje 50 pozycji, a lista plików nie ma
      // stronicowania — bierzemy maksymalną dozwoloną porcję, żeby przy większym
      // folderze nie chować plików bez śladu
      const params: { folder_id?: number; search?: string; limit?: number } = { limit: 200 };
      if (folderId !== null) params.folder_id = folderId;
      if (searchQuery) params.search = searchQuery;

      const res = await filesApi.list(params);
      setFiles(res || []);
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, currentFolderId]);

  // Wejście do innego folderu MUSI najpierw wyczyścić widok. Bez tego przez ułamek
  // sekundy widać jeszcze listę plików z folderu, z którego wychodzimy — a użytkownik
  // czeka już na zawartość nowego. Czyścimy też zaznaczenie, żeby nie przenieść
  // przypadkiem plików, których nie widać.
  const resetFileView = () => {
    setFiles([]);
    setSelectedIds([]);
    setLoading(true);
  };

  // Nawigacja ustawia tylko stan — pliki pobiera efekt reagujący na zmianę
  // folderu. Jedno źródło ładowania oznacza brak wyścigu między ładowaniem
  // z kliknięcia a ładowaniem startowym (to on podmieniał listę na katalog główny).
  const navigateToFolder = (folder: Folder) => {
    setCurrentFolderId(folder.id);
    setBreadcrumbs(prev => [...prev, { id: folder.id, name: folder.name }]);
    resetFileView();
  };

  // Skok do folderu ze ścieżki nawigacji.
  //
  // `index` to pozycja KLIKNIĘTEGO folderu, więc ścieżkę tniemy tuż ZA nim
  // (slice(0, index + 1)). Wcześniej było slice(0, index), czyli kliknięty folder
  // wypadał z wyniku i nawigacja cofała o jeden poziom za daleko — z drugiego
  // poziomu zagnieżdżenia klik w folder nadrzędny lądował w katalogu głównym.
  const navigateToBreadcrumb = (index: number) => {
    const newBreadcrumbs = breadcrumbs.slice(0, index + 1);
    const folderId = newBreadcrumbs[newBreadcrumbs.length - 1]?.id ?? null;
    setBreadcrumbs(newBreadcrumbs);
    setCurrentFolderId(folderId);
    resetFileView();
  };

  // Navigate to root
  const navigateToRoot = () => {
    setCurrentFolderId(null);
    setBreadcrumbs([]);
    resetFileView();
  };

  // Handle file upload — obsługa wielu plików naraz.
  // Wysyłamy sekwencyjnie (jeden POST na plik): backend przyjmuje jeden plik
  // na żądanie, a dyspozytor i tak przetwarza 1 plik naraz. Sekwencyjnie jest
  // łagodniej dla backendu i transferu SSH, a postęp jest czytelny.
  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    const filesToUpload = Array.from(fileList);
    // Reset inputu, aby ponowny wybór tych samych plików znów wyzwolił onChange
    event.target.value = '';

    setUploading(true);
    setUploadItems(filesToUpload.map((f) => ({ name: f.name, status: 'pending' as const })));

    let errorCount = 0;
    for (let i = 0; i < filesToUpload.length; i++) {
      const file = filesToUpload[i];
      setUploadItems((prev) =>
        prev.map((it, idx) => (idx === i ? { ...it, status: 'uploading' } : it))
      );
      try {
        const formData = new FormData();
        formData.append('file', file);
        // Upload do BIEŻĄCEGO folderu (tego, który użytkownik przegląda)
        if (currentFolderId !== null) {
          formData.append('folder_id', String(currentFolderId));
        }
        await filesApi.upload(formData);
        setUploadItems((prev) =>
          prev.map((it, idx) => (idx === i ? { ...it, status: 'done' } : it))
        );
      } catch (err) {
        errorCount++;
        const msg = err instanceof Error ? err.message : 'Błąd wgrywania';
        console.error(`Upload failed (${file.name}):`, err);
        setUploadItems((prev) =>
          prev.map((it, idx) => (idx === i ? { ...it, status: 'error', error: msg } : it))
        );
      }
      // Odśwież listę na bieżąco — pliki pojawiają się w miarę wgrywania
      loadFiles(currentFolderId);
    }

    setUploading(false);
    loadFolders();
    // Wszystko OK → zamknij modal i wyczyść; były błędy → zostaw raport widoczny
    if (errorCount === 0) {
      setShowUploadModal(false);
      setUploadItems([]);
    }
  };

  // Otwórz popup tworzenia folderu; dla podfolderu pobierz role odziedziczone
  const openCreateFolderModal = async () => {
    setInheritedPerms([]);
    setShowCreateFolderModal(true);
    if (currentFolderId !== null) {
      try {
        const res = await foldersApi.effectivePermissions(currentFolderId);
        setInheritedPerms(res || []);
      } catch (err) {
        console.error('Load inherited permissions failed:', err);
      }
    }
  };

  // Handle folder creation
  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return;

    setFolderCreating(true);
    try {
      await foldersApi.create({
        name: newFolderName,
        parent_id: currentFolderId ?? undefined, // Parent is current folder (or undefined for root)
      });

      setNewFolderName('');
      setShowCreateFolderModal(false);
      loadFolders();
      loadFiles(currentFolderId);
    } catch (err) {
      console.error('Create folder failed:', err);
      alert('Tworzenie folderu nie powiodło się.');
    } finally {
      setFolderCreating(false);
    }
  };

  // Delete folder
  const handleDeleteFolder = async (folderId: number) => {
    if (!confirm('Czy na pewno usunąć ten folder? Pliki wewnątrz zostaną przeniesione do roota.')) return;

    try {
      await foldersApi.delete(folderId);
      loadFolders();
      loadFiles(currentFolderId);
      if (currentFolderId === folderId) {
        navigateToRoot();
      }
    } catch (err) {
      console.error('Delete folder failed:', err);
      alert('Usunięcie folderu nie powiodło się.');
    }
  };

  // ---- Zmiana nazwy folderu (admin) ----
  const openRename = (folder: Folder) => {
    setRenameFolder(folder);
    setRenameValue(folder.name);
  };

  const submitRename = async () => {
    if (!renameFolder || !renameValue.trim() || renameValue.trim() === renameFolder.name) return;
    setRenaming(true);
    try {
      await foldersApi.rename(renameFolder.id, renameValue.trim());
      setRenameFolder(null);
      loadFolders();
      // ścieżki w okruszkach mogły się zmienić
      setBreadcrumbs((prev) =>
        prev.map((b) => (b.id === renameFolder.id ? { ...b, name: renameValue.trim() } : b))
      );
    } catch (err: any) {
      alert(err?.message || 'Zmiana nazwy nie powiodła się.');
    } finally {
      setRenaming(false);
    }
  };

  // ---- Przenoszenie plików ----
  const toggleSelect = (id: number) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const submitMove = async () => {
    if (!moveTarget || moveTarget.length === 0) return;
    const target = moveFolderId === '' ? null : Number(moveFolderId);
    setMoving(true);
    try {
      const res = await filesApi.move(moveTarget, target);
      if (res.skipped?.length) {
        alert(
          `Przeniesiono: ${res.moved.length}. Pominięto ${res.skipped.length}:\n` +
          res.skipped.map((s) => `• plik ${s.file_id}: ${s.powod}`).join('\n')
        );
      }
      setMoveTarget(null);
      setSelectedIds([]);
      loadFolders();
      loadFiles(currentFolderId);
    } catch (err: any) {
      alert(err?.message || 'Przeniesienie nie powiodło się.');
    } finally {
      setMoving(false);
    }
  };

  // ---- Uprawnienia folderu (RBAC) ----
  // Pobierz uprawnienia folderu: własne (bezpośrednie), efektywne (z dziedziczeniem)
  // oraz odziedziczone (efektywne folderu nadrzędnego).
  const reloadPerms = async (folder: Folder) => {
    const [direct, eff, inh] = await Promise.all([
      foldersApi.listPermissions(folder.id),
      foldersApi.effectivePermissions(folder.id),
      folder.parent_id != null
        ? foldersApi.effectivePermissions(folder.parent_id)
        : Promise.resolve([] as { role: string; access_level: string }[]),
    ]);
    setPermissions(direct || []);
    setPermEffective(eff || []);
    setPermInherited(inh || []);
  };

  const openPermissions = async (folder: Folder) => {
    setPermFolder(folder);
    setPermissions([]);
    setPermEffective([]);
    setPermInherited([]);
    setPermLoading(true);
    try {
      await reloadPerms(folder);
    } catch (err) {
      console.error('Load permissions failed:', err);
    } finally {
      setPermLoading(false);
    }
  };

  const handleAddPermission = async () => {
    if (!permFolder) return;
    try {
      await foldersApi.addPermission(permFolder.id, {
        role: newPermRole,
        access_level: newPermAccess,
      });
      await reloadPerms(permFolder);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Nie udało się dodać uprawnienia.');
    }
  };

  const handleDeletePermission = async (permId: number) => {
    if (!permFolder) return;
    try {
      await foldersApi.deletePermission(permFolder.id, permId);
      await reloadPerms(permFolder);
    } catch (err) {
      console.error('Delete permission failed:', err);
      alert('Nie udało się usunąć uprawnienia.');
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

  // JEDYNE miejsce, które pobiera listę plików: reaguje na zmianę folderu i na
  // wyszukiwarkę (oraz na montowanie strony). Opóźnienie stosujemy wyłącznie przy
  // pisaniu w wyszukiwarce — zmiana folderu ma być natychmiastowa.
  //
  // `loadFiles` celowo NIE jest zależnością: useCallback odtwarza tę funkcję przy
  // każdej zmianie folderu, więc efekt uruchamiałby się po raz drugi i ładował
  // katalog główny (stąd dawne miganie listy roota).
  const poprzednieSzukanie = useRef(searchQuery);
  useEffect(() => {
    const pisanie = poprzednieSzukanie.current !== searchQuery;
    poprzednieSzukanie.current = searchQuery;
    const timeout = setTimeout(() => loadFiles(currentFolderId), pisanie ? 300 : 0);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, currentFolderId]);

  // Drzewo folderów ładujemy raz — nie zależy od bieżącego folderu
  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  // Dozwolone rozszerzenia — przy błędzie zostaje wartość startowa, żeby okno
  // wysyłki dało się otworzyć mimo niedostępnych ustawień.
  useEffect(() => {
    settingsApi.session()
      .then((s) => {
        if (Array.isArray(s?.allowed_extensions) && s.allowed_extensions.length > 0) {
          setAllowedExts(s.allowed_extensions);
        }
      })
      .catch(() => {});
  }, []);

  // Deep-link z Listy dostępów: /dashboard/files?folder=<id> — wejdź do folderu.
  // Stosujemy raz, po załadowaniu drzewa folderów (potrzebne do breadcrumbów).
  useEffect(() => {
    if (deepLinkDone.current || folders.length === 0) return;
    const param = searchParams.get('folder');
    if (!param) return;
    const id = parseInt(param, 10);
    if (Number.isNaN(id)) return;
    const target = findFolder(folders, id);
    if (!target) return;
    deepLinkDone.current = true;
    // zbuduj breadcrumbs, idąc w górę po parent_id
    const crumbs: { id: number; name: string }[] = [];
    let cur: Folder | null = target;
    while (cur) {
      crumbs.unshift({ id: cur.id, name: cur.name });
      cur = cur.parent_id != null ? findFolder(folders, cur.parent_id) : null;
    }
    setCurrentFolderId(id);
    setBreadcrumbs(crumbs);
  }, [searchParams, folders, loadFiles]);

  // Normalizuj wybór w formularzu uprawnień: rola z dziedziczonym/własnym Zapisem
  // znika z listy (nic nie da się dodać), a rola z Odczytem może być tylko
  // podniesiona do Zapisu (dodanie Odczytu byłoby no-opem).
  useEffect(() => {
    const effByRole: Record<string, string> = {};
    permEffective.forEach((p) => { effByRole[p.role] = p.access_level; });
    const avail = assignableRoles.filter((r) => accessRank(effByRole[r.value]) < 2);
    if (avail.length === 0) return;
    let role = newPermRole;
    if (!avail.some((r) => r.value === role)) {
      role = avail[0].value;
      setNewPermRole(role);
    }
    if (accessRank(effByRole[role]) === 1 && newPermAccess !== 'write') {
      setNewPermAccess('write');
    }
  }, [permEffective, newPermRole, newPermAccess, assignableRoles]);

  useEffect(() => {
    docSchemasApi
      .list()
      .then((sch) => setKategorie(Object.fromEntries((sch || []).map((x: any) => [x.slug, x.name]))))
      .catch(() => { /* brak słownika = pokażemy slug */ });
  }, []);

  const etykietaKategorii = useCallback(
    (slug: string | null | undefined) => {
      if (!slug || slug === 'inny') return '—';
      return kategorie[slug] || slug;
    },
    [kategorie],
  );

  // Top folders (root or current folder children)
  // Foldery pokazujemy alfabetycznie. localeCompare z 'pl' układa polskie znaki
  // we właściwej kolejności (ą po a, ł po l), czego zwykłe sortowanie po kodach
  // znaków nie robi — wypchnęłoby je na koniec listy.
  const alfabetycznie = (a: Folder, b: Folder) => a.name.localeCompare(b.name, 'pl');
  const rootFolders = folders.filter(f => f.parent_id === null).sort(alfabetycznie);
  const currentFolderChildren = folders
    .filter(f => f.parent_id === currentFolderId)
    .sort(alfabetycznie);

  // Get current folder name for display
  const currentFolderName = currentFolderId
    ? findFolder(folders, currentFolderId)?.name || ''
    : '';

  // Czy użytkownik może zapisywać w bieżącym folderze (admin wszędzie).
  // Root (currentFolderId === null) — tylko admin.
  const canWriteHere = isAdmin || (findFolder(folders, currentFolderId)?.can_write ?? false);

  // --- Modal uprawnień: mapy poziomów po roli (dziedziczone + efektywne) ---
  const permInhByRole: Record<string, string> = {};
  permInherited.forEach((p) => { permInhByRole[p.role] = p.access_level; });
  const permEffByRole: Record<string, string> = {};
  permEffective.forEach((p) => { permEffByRole[p.role] = p.access_level; });
  // Formularz „Dodaj": tylko role/poziomy, które realnie coś zmienią.
  // Rola z efektywnym Zapisem (max) znika; rola z Odczytem może iść tylko do Zapisu.
  const permAvailableRoles = assignableRoles.filter(
    (r) => accessRank(permEffByRole[r.value]) < 2
  );
  const permAvailableLevels =
    accessRank(permEffByRole[newPermRole]) === 1 ? ['write'] : ['read', 'write'];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Nagłówek strony (wzorzec jak Dashboard) */}
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Eksplorator plików</h1>

      {/* Moduł: ścieżka folderu + akcje (bez nagłówka → niższy) */}
      <div className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center justify-between gap-3">
          {/* Breadcrumbs (ścieżka od root) */}
          <div className="flex items-center space-x-2 text-sm min-w-0 overflow-x-auto">
            <button
              onClick={navigateToRoot}
              className={`text-blue-600 hover:underline whitespace-nowrap ${currentFolderId === null ? 'font-semibold' : ''}`}
            >
              🏠 Root
            </button>
            {breadcrumbs.map((crumb, index) => (
              <span key={index} className="flex items-center whitespace-nowrap">
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

          {/* Akcje */}
          {(isAdmin || canWriteHere) && (
            <div className="flex gap-2 shrink-0">
              {isAdmin && (
                <button
                  onClick={openCreateFolderModal}
                  className="text-blue-600 hover:text-blue-800 hover:underline px-2 py-2 transition-colors"
                >
                  + Nowy folder
                </button>
              )}
              {canWriteHere && (
                <button
                  onClick={() => setShowUploadModal(true)}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
                  disabled={uploading}
                  title={currentFolderId === null ? 'Wybierz folder, aby wgrać pliki' : undefined}
                >
                  {uploading ? 'Wczytywanie...' : '⬆️ Prześlij pliki'}
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Folders section — pokazuj tylko, gdy są foldery do wyświetlenia */}
        {(currentFolderId === null ? rootFolders : currentFolderChildren).length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-700">📁 Foldery</h2>
              {isAdmin && (
                <span className="text-xs text-gray-400">
                  {currentFolderId === null ? 'Foldery główne' : `Podfoldery`}
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {(currentFolderId === null ? rootFolders : currentFolderChildren).map((folder) => (
                <div
                  key={folder.id}
                  // h-full: kafelki w rzędzie mają wspólną wysokość, wyznaczoną przez
                  // najdłuższą nazwę — inaczej po zawinięciu tekstu rząd robi się poszarpany.
                  // relative: ikony akcji leżą NAD kafelkiem (zob. niżej), nie obok treści.
                  className="relative bg-white p-4 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow group h-full"
                >
                  <button
                    onClick={() => navigateToFolder(folder)}
                    className="w-full text-left"
                  >
                    {/* Rząd z ikoną folderu zostawia miejsce na ikony akcji (pr-20),
                        żeby po najechaniu nic na siebie nie nachodziło. Nazwa i ścieżka
                        poniżej korzystają z PEŁNEJ szerokości kafelka. */}
                    <div className={`text-3xl mb-2 ${isAdmin ? 'pr-20' : ''}`}>📁</div>
                    <div className="font-medium text-gray-800 break-words">{folder.name}</div>
                    <div className="text-xs text-gray-500 break-words">{folder.path}</div>
                    <div className="text-xs text-gray-500">Liczba plików: {folder.file_count ?? 0}</div>
                  </button>
                  {isAdmin && (
                    // Ikony ukryte przez `opacity-0` NADAL zajmowały miejsce w układzie,
                    // więc kolumna z nazwą była węższa o ich szerokość — nazwy łamały się
                    // na kilka wierszy mimo wolnego miejsca po prawej. Wyjęcie ich z toku
                    // dokumentu (absolute) oddaje tę szerokość tekstowi i nie powoduje
                    // przeskoku układu przy najechaniu.
                    <div className="absolute top-3 right-3 flex items-center opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => { e.stopPropagation(); openRename(folder); }}
                        className="text-gray-400 hover:text-blue-600 p-1"
                        title="Zmień nazwę folderu"
                      >
                        ✏️
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); openPermissions(folder); }}
                        className="text-gray-400 hover:text-blue-600 p-1"
                        title="Uprawnienia folderu"
                      >
                        🔒
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteFolder(folder.id); }}
                        className="text-red-400 hover:text-red-600 p-1"
                        title="Usuń folder"
                      >
                        🗑️
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {komunikat && (
          <div className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
            <span>{komunikat}</span>
            <button onClick={() => setKomunikat('')} className="text-green-700 hover:text-green-900">✕</button>
          </div>
        )}

        {/* Files section */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-gray-700">📄 Pliki</h2>
              {selectedIds.length > 0 && (
                <>
                  <span className="text-sm text-gray-500">zaznaczono: {selectedIds.length}</span>
                  {/* Jeden przycisk zamiast listy akcji: operacji zbiorczych będzie
                      przybywać, a pasek nad tabelą nie jest miejscem na ich katalog. */}
                  <div className="relative">
                    <button
                      onClick={() => setOknoAkcji((o) => !o)}
                      className="text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      ⚙ Wykonaj akcję na zaznaczonych ▾
                    </button>
                    {oknoAkcji && (
                      <div className="absolute left-0 z-20 mt-1 w-64 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                        <button
                          onClick={() => { setOknoAkcji(false); setMoveTarget(selectedIds); setMoveFolderId(''); }}
                          className="block w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
                        >
                          📂 Przenieś do folderu
                        </button>
                        <button
                          onClick={() => { setOknoAkcji(false); setRenameTarget(selectedIds); }}
                          className="block w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
                        >
                          🏷 Nadaj nazwy zgodne z kategorią
                        </button>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => setSelectedIds([])}
                    className="text-sm text-gray-400 hover:text-gray-600"
                  >
                    wyczyść
                  </button>
                </>
              )}
            </div>
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
                    {(isAdmin || canWriteHere) && (
                      <th className="px-4 py-3 w-10">
                        <input
                          type="checkbox"
                          checked={files.length > 0 && selectedIds.length === files.length}
                          onChange={(e) => setSelectedIds(e.target.checked ? files.map((f) => f.id) : [])}
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          title="Zaznacz wszystkie"
                        />
                      </th>
                    )}
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ikona</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nazwa</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rozmiar</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Kategoria</th>
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
                      {(isAdmin || canWriteHere) && (
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(file.id)}
                            onChange={() => toggleSelect(file.id)}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                        </td>
                      )}
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
                      {/* Kategoria zamiast statusu: status pilnuje się w Kolejce plików,
                          a na liście dokumentów szuka się rodzaju dokumentu. */}
                      <td className="px-4 py-3">
                        {file.doc_type && file.doc_type !== 'inny' ? (
                          <span className="rounded-full bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-800">
                            {etykietaKategorii(file.doc_type)}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400">nierozpoznana</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {dataLokalna(file.created_at)}
                        {' '}
                        {godzinaLokalna(file.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        {/* Akcje: ikona NAD podpisem — układ jawny (flex-col), żeby
                            wszystkie trzy wyglądały tak samo niezależnie od długości słowa */}
                        <div className="flex items-start space-x-4">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                            className="flex flex-col items-center gap-0.5 text-blue-600 hover:text-blue-800 text-sm"
                          >
                            <span className="text-base leading-none">⬇️</span>
                            <span>Pobierz</span>
                          </button>
                          {(isAdmin || canWriteHere) && (
                            <>
                              <button
                                onClick={(e) => { e.stopPropagation(); setMoveTarget([file.id]); setMoveFolderId(''); }}
                                className="flex flex-col items-center gap-0.5 text-blue-600 hover:text-blue-800 text-sm"
                              >
                                <span className="text-base leading-none">📂</span>
                                <span>Przenieś</span>
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDelete(file.id); }}
                                className="flex flex-col items-center gap-0.5 text-red-600 hover:text-red-800 text-sm"
                              >
                                <span className="text-base leading-none">🗑️</span>
                                <span>Usuń</span>
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {files.length === 0 && !loading && (
                    <tr>
                      <td className="px-4 py-8 text-center text-gray-500" colSpan={(isAdmin || canWriteHere) ? 7 : 6}>
                        Brak plików w tym folderze
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
                    {(isAdmin || canWriteHere) && (
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
                  Brak plików w tym folderze
                </div>
              )}
            </div>
          )}
          {loading && viewMode === 'grid' && (
            <div className="text-center text-gray-500 py-8">Ładowanie...</div>
          )}
        </div>
      </div>

      {/* Create Folder Modal */}
      {showCreateFolderModal && isAdmin && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-bold text-gray-800 mb-4">
              📁 Nowy folder
            </h2>
            <p className="text-sm text-gray-600 mb-2">
              Tworzony w: <strong>
                {currentFolderName || 'Root'}
              </strong>
            </p>
            <input
              type="text"
              placeholder="Nazwa folderu"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreateFolder(); }}
              className="w-full border border-gray-300 rounded-md p-2 mb-4"
              autoFocus
            />

            {/* Role odziedziczone po folderze nadrzędnym (tylko dla podfolderu, do wglądu) */}
            {currentFolderId !== null && (
              <div className="mb-4">
                <p className="text-xs text-gray-500 mb-1">
                  Nowy podfolder odziedziczy dostęp folderu nadrzędnego:
                </p>
                {inheritedPerms.length === 0 ? (
                  <p className="text-xs text-gray-400">
                    Brak ról z dostępem (poza administratorem).
                  </p>
                ) : (
                  <ul className="text-sm text-gray-700 border border-gray-200 rounded-md divide-y divide-gray-100">
                    {inheritedPerms.map((p) => (
                      <li key={p.role} className="px-3 py-1.5">
                        {roleLabel(roles, p.role)}
                        <span className="text-gray-400"> · </span>
                        <span className="text-gray-600">
                          {ACCESS_LABELS[p.access_level] || p.access_level}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-[11px] text-gray-400 mt-1">
                  Dostęp dziedziczony (tylko do wglądu). Zmienisz go później przez 🔒 na folderze.
                </p>
              </div>
            )}
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => { setShowCreateFolderModal(false); setNewFolderName(''); setInheritedPerms([]); }}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                disabled={folderCreating}
              >
                Anuluj
              </button>
              <button
                onClick={handleCreateFolder}
                className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
                disabled={folderCreating || !newFolderName.trim()}
              >
                {folderCreating ? 'Tworzenie...' : 'Utwórz'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Permissions Modal (RBAC) */}
      {permFolder && isAdmin && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-bold text-gray-800">🔒 Uprawnienia folderu</h2>
              <button
                onClick={() => setPermFolder(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Folder: <strong>{permFolder.name}</strong> ({permFolder.path})
            </p>
            <p className="text-xs text-gray-500 mb-4">
              Rola z uprawnieniem widzi pliki w tym folderze <strong>i jego
              podfolderach</strong>. Uprawnienia oznaczone „(dziedziczone)" pochodzą
              z folderu nadrzędnego — zmienisz je na tamtym folderze. Administrator
              ma zawsze pełny dostęp; pliki w folderze głównym (root) widzi tylko
              administrator.
            </p>

            {/* Lista uprawnień efektywnych: własne (usuwalne) + dziedziczone (do wglądu) */}
            <div className="mb-4">
              {permLoading ? (
                <div className="text-sm text-gray-500 py-3">Ładowanie...</div>
              ) : permEffective.length === 0 ? (
                <div className="text-sm text-gray-500 py-3 border border-dashed border-gray-200 rounded-md text-center">
                  Brak uprawnień — tylko administrator widzi ten folder.
                </div>
              ) : (
                <ul className="divide-y divide-gray-100 border border-gray-200 rounded-md">
                  {permEffective.map((eff) => {
                    // Własne rozszerzenie = bezpośrednie uprawnienie WYŻSZE niż dziedziczone.
                    // Bezpośrednie ≤ dziedziczone jest zdominowane → traktujemy jak dziedziczone.
                    const direct = permissions.find((p) => p.role === eff.role);
                    const isOwn =
                      !!direct &&
                      accessRank(direct.access_level) > accessRank(permInhByRole[eff.role]);
                    return (
                      <li key={eff.role} className="flex items-center justify-between px-3 py-2 text-sm">
                        <span className="text-gray-800">
                          {roleLabel(roles, eff.role)}
                          <span className="text-gray-400"> · </span>
                          <span className="text-gray-600">
                            {ACCESS_LABELS[eff.access_level] || eff.access_level}
                          </span>
                          {!isOwn && (
                            <span className="ml-2 text-xs text-gray-400">
                              (dziedziczone z nadrzędnego)
                            </span>
                          )}
                        </span>
                        {isOwn && direct ? (
                          <button
                            onClick={() => handleDeletePermission(direct.id)}
                            className="text-red-500 hover:text-red-700 text-xs"
                          >
                            Usuń
                          </button>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* Formularz dodania uprawnienia — tylko role/poziomy, które coś zmienią.
                Można wyłącznie ROZSZERZAĆ dostęp (dodać rolę lub podnieść Odczyt→Zapis);
                zawężać poniżej dziedziczonego nie można. */}
            {permAvailableRoles.length === 0 ? (
              <div className="border-t border-gray-100 pt-4 text-xs text-gray-500">
                Wszystkie role mają już maksymalny dostęp (Zapis) — dziedziczony lub
                własny. Nie ma czego dodać.
              </div>
            ) : (
              <div className="flex items-end gap-2 border-t border-gray-100 pt-4">
                <label className="flex-1 text-xs text-gray-500">
                  Rola
                  <select
                    value={newPermRole}
                    onChange={(e) => setNewPermRole(e.target.value)}
                    className="mt-1 w-full border border-gray-300 rounded-md p-2 text-sm text-gray-800"
                  >
                    {permAvailableRoles.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-gray-500">
                  Poziom
                  <select
                    value={newPermAccess}
                    onChange={(e) => setNewPermAccess(e.target.value)}
                    className="mt-1 border border-gray-300 rounded-md p-2 text-sm text-gray-800"
                  >
                    {permAvailableLevels.map((lvl) => (
                      <option key={lvl} value={lvl}>{ACCESS_LABELS[lvl]}</option>
                    ))}
                  </select>
                </label>
                <button
                  onClick={handleAddPermission}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 text-sm"
                >
                  Dodaj
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && canWriteHere && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-bold text-gray-800 mb-2">Prześlij pliki</h2>
            <p className="text-sm text-gray-600 mb-1">
              Dozwolone typy: {allowedExts.map((e) => e.toUpperCase()).join(', ')} (max
              100MB). Możesz wybrać wiele plików naraz.
            </p>
            <p className="text-sm text-gray-600 mb-4">
              Docelowy folder: <strong>
                {currentFolderName || 'Root (brak folderu)'}
              </strong>
            </p>
            <input
              type="file"
              multiple
              accept={allowedExts.map((e) => `.${e}`).join(',')}
              onChange={handleUpload}
              className="w-full border border-gray-300 rounded-md p-2"
              disabled={uploading}
            />

            {/* Postęp wgrywania (jeden wiersz na plik) */}
            {uploadItems.length > 0 && (
              <div className="mt-4">
                <div className="text-sm font-medium text-gray-700 mb-2">
                  Postęp: {uploadItems.filter((it) => it.status === 'done').length}/
                  {uploadItems.length} wgranych
                  {uploadItems.some((it) => it.status === 'error') && (
                    <span className="text-red-600">
                      {' '}
                      ({uploadItems.filter((it) => it.status === 'error').length} z błędem)
                    </span>
                  )}
                </div>
                <ul className="max-h-48 overflow-y-auto divide-y divide-gray-100 border border-gray-200 rounded-md">
                  {uploadItems.map((it, idx) => (
                    <li key={idx} className="flex items-start gap-2 px-3 py-2 text-sm">
                      <span className="mt-0.5">
                        {it.status === 'done'
                          ? '✅'
                          : it.status === 'error'
                          ? '❌'
                          : it.status === 'uploading'
                          ? '⏳'
                          : '⬜'}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="block truncate text-gray-800" title={it.name}>
                          {it.name}
                        </span>
                        {it.status === 'error' && it.error && (
                          <span className="block text-xs text-red-600">{it.error}</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end space-x-2 mt-4">
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  setUploadItems([]);
                }}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
                disabled={uploading}
              >
                {uploading
                  ? 'Wgrywanie...'
                  : uploadItems.length > 0
                  ? 'Zamknij'
                  : 'Anuluj'}
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
                  {czasLokalny(selectedFile.created_at, { dateStyle: 'long', timeStyle: 'short' })}
                </dd>
              </div>
              {selectedFile.folder && (
                <div>
                  <dt className="text-sm text-gray-500">Folder</dt>
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
              {(isAdmin || canWriteHere) && (
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

      {/* Zmiana nazwy folderu (admin) */}
      {renameFolder && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">Zmień nazwę folderu</h2>
            <input
              type="text"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitRename(); }}
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {(() => {
              const subs = folders.filter((f) => f.path.startsWith(renameFolder.path + '/')).length;
              return (
                <p className="text-xs text-gray-500 mt-2">
                  Zmiana obejmie ścieżkę tego folderu
                  {subs > 0 ? ` oraz ${subs} podfolder(ów)` : ''}. Pliki i uprawnienia pozostają
                  przypisane bez zmian.
                </p>
              );
            })()}
            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={() => setRenameFolder(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                Anuluj
              </button>
              <button
                onClick={submitRename}
                disabled={renaming || !renameValue.trim() || renameValue.trim() === renameFolder.name}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed"
              >
                {renaming ? 'Zapisywanie…' : 'Zapisz'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Przeniesienie plików do innego folderu */}
      {renameTarget && (
        <RenameDialog
          fileIds={renameTarget}
          etykietaKategorii={etykietaKategorii}
          onClose={() => setRenameTarget(null)}
          onDone={(tekst) => {
            setRenameTarget(null);
            setSelectedIds([]);
            setKomunikat(tekst);
            loadFiles();
          }}
        />
      )}

      {moveTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold text-gray-800 mb-1">
              Przenieś {moveTarget.length === 1 ? 'plik' : `pliki (${moveTarget.length})`}
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              Wybierz folder docelowy. Widoczne są tylko foldery z prawem zapisu.
            </p>
            <select
              value={moveFolderId}
              onChange={(e) => setMoveFolderId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-white focus:ring-2 focus:ring-blue-500"
            >
              <option value="">{isAdmin ? '— katalog główny —' : '— wybierz folder —'}</option>
              {folders
                .filter((f) => (isAdmin || f.can_write) && f.id !== currentFolderId)
                .map((f) => (
                  <option key={f.id} value={String(f.id)}>{f.path}</option>
                ))}
            </select>
            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={() => setMoveTarget(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                Anuluj
              </button>
              <button
                onClick={submitMove}
                disabled={moving || (!isAdmin && moveFolderId === '')}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed"
              >
                {moving ? 'Przenoszenie…' : 'Przenieś'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Wrapper z granicą Suspense — wymagane przez useSearchParams() w Next.js 14
export default function FilesPage() {
  return (
    <Suspense fallback={<div className="p-6 text-gray-500">Ładowanie...</div>}>
      <FilesPageInner />
    </Suspense>
  );
}