'use client';

import { useSearchParams } from 'next/navigation';
import { useState, useEffect, useCallback, useMemo, useRef, Suspense } from 'react';

import { FileTypeIcon, rozmiarPliku } from '@/components/file-type-icon';
import {
  IconChevronDown, IconClose, IconDoc, IconDownload, IconEdit, IconEye, IconFolder,
  IconGrid, IconHome, IconList, IconLock, IconMove, IconPlus, IconTrash, IconUpload,
} from '@/components/icons';
import { RenameDialog } from '@/components/rename-dialog';
import {
  Badge, Button, Card, EmptyState, Field, IconButton, Modal, PageHeader, RowActions,
  Sub, Table, Td, Th, inputClass,
} from '@/components/ui/primitives';
import { docSchemasApi, filesApi, foldersApi, settingsApi } from '@/lib/api';
import type { SortKey, SortOrder } from '@/lib/api';
import { czasLokalny, kiedy } from '@/lib/czas';
import { ROLE_ADMIN, isAdmin as czyAdmin, roleLabel, useRoles } from '@/lib/roles';
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

// Ile pozycji bierzemy jednym żądaniem. Lista nie jest stronicowana po stronie
// backendu, więc to jest zarazem twardy sufit widoczności — gdy folder go dobije,
// mówimy o tym pod tabelą, zamiast po cichu chować resztę.
const LIMIT_LISTY = 200;

const NA_STRONIE = [10, 25, 50, 100];

/** Kropka stanu przy wgrywanym pliku — kolorem, nie emoji (te same powody co
 *  przy ikonach typów plików: emoji wygląda inaczej na każdym systemie). */
const STAN_WGRYWANIA: Record<string, string> = {
  pending: 'bg-app-line',
  uploading: 'bg-app-blue animate-pulse',
  done: 'bg-app-green',
  error: 'bg-app-danger',
};

const OPIS_WGRYWANIA: Record<string, string> = {
  pending: 'oczekuje',
  uploading: 'wgrywanie…',
  done: 'wgrany',
  error: 'błąd',
};

/** 1 plik, 2 pliki, 5 plików. */
function odmianaPlikow(n: number): string {
  if (n === 1) return 'plik';
  const ost = n % 10;
  const dwie = n % 100;
  return ost >= 2 && ost <= 4 && (dwie < 10 || dwie >= 20) ? 'pliki' : 'plików';
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
  // Widok folderow trzymamy OSOBNO od widoku plikow: to dwie rozne listy i
  // czesto chce sie je ogladac inaczej — foldery jako kafelki (latwiej trafic),
  // pliki jako liste (wiecej kolumn na ekranie).
  const [folderView, setFolderView] = useState<ViewMode>('grid');
  // Stronicowanie jest po stronie przeglądarki — dzielimy listę, którą już mamy.
  const [strona, setStrona] = useState(1);
  const [naStronie, setNaStronie] = useState(25);
  // Kolejność listy plików. Sortuje backend, tu trzymamy tylko wybór użytkownika.
  const [sortBy, setSortBy] = useState<SortKey>('name');
  const [kierunek, setKierunek] = useState<SortOrder>('asc');
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
      // Sortowanie idzie do backendu, a nie robimy go po pobraniu: lista ma limit,
      // więc układanie w przeglądarce porządkowałoby tylko pobraną porcję.
      const params: {
        folder_id?: number; search?: string; limit?: number;
        sort_by?: SortKey; order?: SortOrder;
      } = { limit: LIMIT_LISTY, sort_by: sortBy, order: kierunek };
      if (folderId !== null) params.folder_id = folderId;
      if (searchQuery) params.search = searchQuery;

      const res = await filesApi.list(params);
      setFiles(res || []);
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, currentFolderId, sortBy, kierunek]);

  // Wejście do innego folderu MUSI najpierw wyczyścić widok. Bez tego przez ułamek
  // sekundy widać jeszcze listę plików z folderu, z którego wychodzimy — a użytkownik
  // czeka już na zawartość nowego. Czyścimy też zaznaczenie, żeby nie przenieść
  // przypadkiem plików, których nie widać.
  const resetFileView = () => {
    setFiles([]);
    setSelectedIds([]);
    setStrona(1);
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

  // Podgląd PDF w nowej karcie. Pobieramy przez fetch, a nie przez zwykły
  // odnośnik, bo endpoint wymaga nagłówka z tokenem — okno otwarte na goły URL
  // dostałoby 401.
  const handlePreview = async (file: File) => {
    const token = localStorage.getItem('auth_token');
    if (!token) return;
    try {
      const response = await fetch(`/api/files/${file.id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Preview failed');
      window.open(URL.createObjectURL(await response.blob()), '_blank');
    } catch {
      alert('Podgląd nie powiódł się.');
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
  }, [searchQuery, currentFolderId, sortBy, kierunek]);

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
  // Kolumny, dla których pierwsze kliknięcie ma układać MALEJĄCO. Przy rozmiarze
  // i dacie szuka się największych i najnowszych, więc zaczynanie od najmniejszych
  // i najstarszych zmuszałoby do drugiego kliknięcia za każdym razem.
  const NAJPIERW_MALEJACO: SortKey[] = ['size', 'date'];

  const sortuj = (kolumna: SortKey) => {
    if (kolumna === sortBy) {
      setKierunek(kierunek === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(kolumna);
      setKierunek(NAJPIERW_MALEJACO.includes(kolumna) ? 'desc' : 'asc');
    }
    // Bez tego po przesortowaniu zostaje się na stronie 4 zupełnie innej listy.
    setStrona(1);
  };

  /** Propsy nagłówka: kierunek podajemy WYŁĄCZNIE aktywnej kolumnie. */
  const naglowek = (kolumna: SortKey) => ({
    sorted: sortBy === kolumna ? kierunek : undefined,
    onSort: () => sortuj(kolumna),
  });

  // Foldery pokazujemy alfabetycznie. localeCompare z 'pl' układa polskie znaki
  // we właściwej kolejności (ą po a, ł po l), czego zwykłe sortowanie po kodach
  // znaków nie robi — wypchnęłoby je na koniec listy.
  // `numeric` porównuje ciągi cyfr wg wartości, więc „Rok 2" stoi przed „Rok 10”.
  // Ta sama reguła obowiązuje pliki (kolacja ICU po stronie bazy) — obie listy
  // na tym ekranie mają układać się tak samo.
  const PORZADEK: Intl.CollatorOptions = { numeric: true };
  const alfabetycznie = (a: Folder, b: Folder) => a.name.localeCompare(b.name, 'pl', PORZADEK);
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

  // Stronicowanie po stronie przeglądarki. Backend oddaje najwyżej `LIMIT_LISTY`
  // pozycji jednym żądaniem, więc nie ma tu drugiego pobrania — dzielimy to,
  // co już mamy. Gdy folder dobije do limitu, mówimy o tym wprost pod tabelą,
  // zamiast po cichu chować resztę.
  const stron = Math.max(1, Math.ceil(files.length / naStronie));
  const stronaBezpieczna = Math.min(strona, stron);
  const widoczne = files.slice((stronaBezpieczna - 1) * naStronie, stronaBezpieczna * naStronie);
  const wszystkieWidoczneZaznaczone =
    widoczne.length > 0 && widoczne.every((f) => selectedIds.includes(f.id));
  const podfoldery = currentFolderId === null ? rootFolders : currentFolderChildren;
  const zaznaczalne = isAdmin || canWriteHere;

  return (
    <div>
      <PageHeader
        title="Eksplorator plików"
        description="Przegląd folderów i dokumentów w systemie."
      />

      {/* Ścieżka folderu + akcje */}
      <Card className="mb-[18px] flex flex-wrap items-center justify-between gap-3 px-[18px] py-3.5">
        <nav className="flex min-w-0 flex-wrap items-center gap-1.5 text-[14px]" aria-label="Ścieżka folderu">
          <button
            onClick={navigateToRoot}
            className={`inline-flex items-center gap-1.5 rounded-ctl px-2 py-1 hover:bg-app-hover ${
              currentFolderId === null ? 'font-bold text-app-blue' : 'text-app-text'
            }`}
          >
            <IconHome size={16} />
            Katalog główny
          </button>
          {breadcrumbs.map((crumb, index) => (
            <span key={crumb.id} className="flex items-center gap-1.5">
              <span className="text-app-muted">/</span>
              <button
                onClick={() => navigateToBreadcrumb(index)}
                className={`rounded-ctl px-2 py-1 hover:bg-app-hover ${
                  index === breadcrumbs.length - 1 ? 'font-bold text-app-blue' : 'text-app-text'
                }`}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </nav>

        {(isAdmin || canWriteHere) && (
          <div className="flex shrink-0 gap-2">
            {isAdmin && (
              <Button onClick={openCreateFolderModal}>
                <IconPlus size={16} />
                Nowy folder
              </Button>
            )}
            {canWriteHere && (
              <Button
                variant="primary"
                onClick={() => setShowUploadModal(true)}
                disabled={uploading}
                title={currentFolderId === null ? 'Wybierz folder, aby wgrać pliki' : undefined}
              >
                <IconUpload size={16} />
                {uploading ? 'Wczytywanie…' : 'Prześlij pliki'}
              </Button>
            )}
          </div>
        )}
      </Card>

      {/* Foldery */}
      {podfoldery.length > 0 && (
        <Card className="mb-[18px] overflow-hidden">
          <div className="flex flex-wrap items-center gap-2.5 px-[18px] py-3.5">
            <h2 className="mr-auto flex items-center gap-2.5 text-[16px] font-bold text-app-text">
              <IconFolder size={18} />
              Foldery
              <span className="text-[11px] font-normal text-app-muted">
                {currentFolderId === null ? 'główne' : 'w tym folderze'}
              </span>
            </h2>
            <WidokToggle wartosc={folderView} zmien={setFolderView} etykieta="Widok folderów" />
          </div>

          {folderView === 'grid' ? (
            <div className="grid grid-cols-1 gap-[18px] px-[18px] pb-[18px] sm:grid-cols-2 xl:grid-cols-4">
              {podfoldery.map((folder) => (
                <div
                  key={folder.id}
                  // relative: ikony akcji leżą NAD kafelkiem (zob. komentarz niżej).
                  className="group relative flex h-full flex-col rounded-card border border-app-line bg-white p-[18px] transition-shadow hover:shadow-card"
                >
                  <button onClick={() => navigateToFolder(folder)} className="flex w-full flex-col gap-3 text-left">
                    {/* Ikona ma WŁASNY wiersz, a nie miejsce obok tekstu. Ikony akcji
                        leżą w tym samym pasie po prawej, więc nazwa folderu dostaje
                        pełną szerokość kafelka. Wcześniej rezerwowaliśmy na akcje stały
                        margines po prawej przez całą wysokość — i „Polityka
                        antymobbingowa" łamała się w środku słowa mimo wolnego miejsca. */}
                    <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[12px] bg-[#fff6e2] text-[#d99b20]">
                      <IconFolder size={22} />
                    </span>
                    <span className="min-w-0">
                      <span className="block break-words text-[14px] font-bold text-app-text">{folder.name}</span>
                      {folder.path !== `/${folder.name}` && (
                        // Dla folderu głównego ścieżka to sama jego nazwa ze slashem —
                        // powtarzanie jej pod spodem nic nie wnosi.
                        <span className="mt-0.5 block break-words text-[11px] text-app-muted">{folder.path}</span>
                      )}
                      <span className="mt-1 block text-[11px] text-app-muted">
                        {folder.file_count ?? 0} {odmianaPlikow(folder.file_count ?? 0)}
                      </span>
                    </span>
                  </button>
                  {isAdmin && (
                    <div className="absolute right-3 top-3 flex items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                      <AkcjeFolderu
                        folder={folder}
                        zmienNazwe={openRename}
                        uprawnienia={openPermissions}
                        usun={handleDeleteFolder}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto border-t border-app-line">
              <Table>
                <thead>
                  <tr>
                    <Th className="w-[62px]">Typ</Th>
                    <Th>Nazwa</Th>
                    {/* W katalogu głównym ścieżka każdego folderu to jego własna
                        nazwa ze slashem — kolumna pełna „/Delegacje" obok „Delegacje"
                        nie niesie nic. Pokazujemy ją dopiero w głębi drzewa. */}
                    {currentFolderId !== null && <Th>Ścieżka</Th>}
                    <Th className="whitespace-nowrap">Liczba plików</Th>
                    <Th className="w-[120px]" />
                  </tr>
                </thead>
                <tbody>
                  {podfoldery.map((folder) => (
                    <tr
                      key={folder.id}
                      className="group cursor-pointer hover:bg-app-hover"
                      onClick={() => navigateToFolder(folder)}
                    >
                      <Td>
                        <span className="grid h-8 w-8 place-items-center rounded-[7px] bg-[#fff6e2] text-[#d99b20]">
                          <IconFolder size={17} />
                        </span>
                      </Td>
                      <Td>
                        <span className="block break-words font-bold text-app-text">{folder.name}</span>
                      </Td>
                      {currentFolderId !== null && (
                        <Td className="break-words text-app-muted">{folder.path}</Td>
                      )}
                      <Td className="whitespace-nowrap text-app-muted">
                        {folder.file_count ?? 0} {odmianaPlikow(folder.file_count ?? 0)}
                      </Td>
                      <Td onClick={(e) => e.stopPropagation()}>
                        {isAdmin && (
                          <RowActions>
                            <AkcjeFolderu
                              folder={folder}
                              zmienNazwe={openRename}
                              uprawnienia={openPermissions}
                              usun={handleDeleteFolder}
                            />
                          </RowActions>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </Card>
      )}

      {komunikat && (
        <div className="mb-[18px] flex items-start justify-between gap-3 rounded-ctl border border-[#bfe6d2] bg-app-greenbg px-4 py-3 text-sm text-[#148a57]">
          <span>{komunikat}</span>
          <button onClick={() => setKomunikat('')} aria-label="Zamknij komunikat">
            <IconClose size={16} />
          </button>
        </div>
      )}

      {/* Pliki */}
      <Card className="mb-[18px] overflow-hidden">
        <div className="flex flex-wrap items-center gap-2.5 border-b border-app-line px-[18px] py-3.5">
          <h2 className="mr-auto flex items-center gap-2.5 text-[16px] font-bold text-app-text">
            <IconDoc size={18} />
            Pliki
          </h2>

          {selectedIds.length > 0 && (
            <div className="flex items-center gap-2.5">
              <span className="text-[12px] text-app-muted">zaznaczono: {selectedIds.length}</span>
              {/* Jeden przycisk zamiast listy akcji: operacji zbiorczych będzie
                  przybywać, a pasek nad tabelą nie jest miejscem na ich katalog. */}
              <div className="relative">
                <Button small onClick={() => setOknoAkcji((o) => !o)}>
                  Wykonaj akcję na zaznaczonych
                  <IconChevronDown size={14} />
                </Button>
                {oknoAkcji && (
                  <div className="absolute left-0 z-20 mt-1 w-64 overflow-hidden rounded-ctl border border-app-line bg-white py-1 shadow-card">
                    <button
                      onClick={() => { setOknoAkcji(false); setMoveTarget(selectedIds); setMoveFolderId(''); }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-app-text hover:bg-app-hover"
                    >
                      <IconMove size={16} />
                      Przenieś do folderu
                    </button>
                    <button
                      onClick={() => { setOknoAkcji(false); setRenameTarget(selectedIds); }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-app-text hover:bg-app-hover"
                    >
                      <IconEdit size={16} />
                      Nadaj nazwy zgodne z kategorią
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={() => setSelectedIds([])}
                className="text-[12px] text-app-muted hover:text-app-text"
              >
                wyczyść
              </button>
            </div>
          )}

          {/* Szerokosc nadaje OPAKOWANIE, nie klasa na polu: `inputClass` niesie
              `w-full`, a Tailwind emituje `.w-full` po `.w-48`, wiec przy rownej
              specyficznosci zwezenie w lancuchu klas przegrywa (pole mialo 1075 px
              zamiast 192 px i lamalo pasek na trzy wiersze). */}
          <span className="w-48 shrink-0">
            <input
              type="text"
              placeholder="Szukaj pliku…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={`${inputClass} h-9`}
              aria-label="Szukaj pliku"
            />
          </span>

          <WidokToggle wartosc={viewMode} zmien={setViewMode} etykieta="Widok listy plików" />
        </div>

        {loading ? (
          <div className="px-[18px] py-10 text-center text-sm text-app-muted">Ładowanie…</div>
        ) : files.length === 0 ? (
          <EmptyState
            title={searchQuery ? 'Brak plików pasujących do wyszukiwania' : 'Brak plików w tym folderze'}
            hint={searchQuery ? 'Spróbuj innego fragmentu nazwy.' : canWriteHere ? 'Użyj przycisku „Prześlij pliki".' : undefined}
          />
        ) : viewMode === 'list' ? (
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  {zaznaczalne && (
                    <Th className="w-[52px]">
                      <input
                        type="checkbox"
                        checked={wszystkieWidoczneZaznaczone}
                        onChange={(e) =>
                          setSelectedIds(
                            e.target.checked
                              // Zaznaczamy TĘ stronę, nie całą listę: pole nad kolumną
                              // odnosi się do tego, co widać, a nie do stu ukrytych wierszy.
                              ? Array.from(new Set([...selectedIds, ...widoczne.map((f) => f.id)]))
                              : selectedIds.filter((id) => !widoczne.some((f) => f.id === id)),
                          )
                        }
                        aria-label="Zaznacz pliki na tej stronie"
                      />
                    </Th>
                  )}
                  <Th className="w-[62px]" {...naglowek('type')}>Typ</Th>
                  <Th {...naglowek('name')}>Nazwa</Th>
                  <Th className="whitespace-nowrap" {...naglowek('size')}>Rozmiar</Th>
                  <Th {...naglowek('category')}>Kategoria</Th>
                  <Th className="whitespace-nowrap" {...naglowek('date')}>Data dodania</Th>
                  <Th className="w-[120px]" />
                </tr>
              </thead>
              <tbody>
                {widoczne.map((file) => (
                  <tr
                    key={file.id}
                    className="group cursor-pointer hover:bg-app-hover"
                    onClick={() => setSelectedFile(file)}
                  >
                    {zaznaczalne && (
                      <Td onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(file.id)}
                          onChange={() => toggleSelect(file.id)}
                          aria-label={`Zaznacz ${file.filename}`}
                        />
                      </Td>
                    )}
                    <Td><FileTypeIcon filename={file.filename} /></Td>
                    <Td>
                      <span className="block break-words font-bold text-app-text">{file.filename}</span>
                      {file.original_filename && file.original_filename !== file.filename && (
                        <Sub>pierwotnie: {file.original_filename}</Sub>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap text-app-muted">{rozmiarPliku(file.size)}</Td>
                    {/* Kategoria zamiast statusu: status pilnuje się w Kolejce plików,
                        a na liście dokumentów szuka się rodzaju dokumentu. */}
                    <Td>
                      {file.doc_type && file.doc_type !== 'inny' ? (
                        <Badge tone="purple">{etykietaKategorii(file.doc_type)}</Badge>
                      ) : (
                        <span className="text-[11px] text-app-muted">nierozpoznana</span>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap text-app-muted">{kiedy(file.created_at)}</Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      <RowActions>
                        <IconButton tone="action" title="Pobierz plik" onClick={() => handleDownload(file)}>
                          <IconDownload size={16} />
                        </IconButton>
                        {zaznaczalne && (
                          <>
                            <IconButton
                              tone="action"
                              title="Przenieś do innego folderu"
                              onClick={() => { setMoveTarget([file.id]); setMoveFolderId(''); }}
                            >
                              <IconMove size={16} />
                            </IconButton>
                            <IconButton tone="danger" title="Usuń plik" onClick={() => handleDelete(file.id)}>
                              <IconTrash size={16} />
                            </IconButton>
                          </>
                        )}
                      </RowActions>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-[18px] p-[18px] md:grid-cols-4 xl:grid-cols-6">
            {widoczne.map((file) => (
              <button
                key={file.id}
                onClick={() => setSelectedFile(file)}
                // `flex h-full flex-col` nie jest ozdobą: przeglądarka centruje
                // pionowo zawartość przycisku, a siatka rozciąga kafelki do wysokości
                // najwyższego w rzędzie — przez co ikona i nazwa w krótszych kafelkach
                // zjeżdżały na środek i cały rząd wyglądał na rozstrojony.
                className="flex h-full flex-col items-start rounded-card border border-app-line bg-white p-4 text-left transition-shadow hover:shadow-card"
              >
                <FileTypeIcon filename={file.filename} size={44} className="mb-3" />
                <span className="block break-words text-[13px] font-bold text-app-text">{file.filename}</span>
                <span className="mt-1 block text-[11px] text-app-muted">{rozmiarPliku(file.size)}</span>
                <span className="mt-0.5 block text-[11px] text-app-muted">{kiedy(file.created_at)}</span>
              </button>
            ))}
          </div>
        )}

        {files.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-app-line px-[18px] py-3.5 text-[12px] text-app-muted">
            <span>
              {widoczne.length === files.length
                ? `${files.length} ${odmianaPlikow(files.length)}`
                : `${(stronaBezpieczna - 1) * naStronie + 1}–${(stronaBezpieczna - 1) * naStronie + widoczne.length} z ${files.length}`}
              {files.length >= LIMIT_LISTY && (
                // Ucięcie musi być widoczne: bez tej informacji lista wygląda na
                // kompletną, a część plików po prostu nie dojechała.
                <span className="ml-1 text-app-danger">
                  (pokazujemy pierwsze {LIMIT_LISTY} — zawęź wyszukiwanie)
                </span>
              )}
            </span>

            {stron > 1 && (
              <span className="flex items-center gap-1.5">
                <Button small disabled={stronaBezpieczna === 1} onClick={() => setStrona(stronaBezpieczna - 1)}>‹</Button>
                <span className="px-1">strona {stronaBezpieczna} z {stron}</span>
                <Button small disabled={stronaBezpieczna === stron} onClick={() => setStrona(stronaBezpieczna + 1)}>›</Button>
              </span>
            )}

            <label className="flex items-center gap-2">
              Pokaż:
              <select
                value={naStronie}
                onChange={(e) => { setNaStronie(Number(e.target.value)); setStrona(1); }}
                className={`${inputClass} h-8 w-auto py-0`}
              >
                {NA_STRONIE.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
        )}
      </Card>

      {/* ------------------------------------------------------------ okna */}

      {showCreateFolderModal && isAdmin && (
        <Modal
          title="Nowy folder"
          onClose={() => { setShowCreateFolderModal(false); setNewFolderName(''); setInheritedPerms([]); }}
          footer={
            <>
              <Button
                onClick={() => { setShowCreateFolderModal(false); setNewFolderName(''); setInheritedPerms([]); }}
                disabled={folderCreating}
              >
                Anuluj
              </Button>
              <Button variant="primary" onClick={handleCreateFolder} disabled={folderCreating || !newFolderName.trim()}>
                {folderCreating ? 'Tworzenie…' : 'Utwórz'}
              </Button>
            </>
          }
        >
          <p className="mb-3 text-[13px] text-app-muted">
            Tworzony w: <strong className="text-app-text">{currentFolderName || 'katalog główny'}</strong>
          </p>
          <Field label="Nazwa folderu">
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreateFolder(); }}
              className={inputClass}
              autoFocus
            />
          </Field>

          {/* Role odziedziczone po folderze nadrzędnym (tylko do wglądu) */}
          {currentFolderId !== null && (
            <div className="mt-4">
              <p className="mb-1 text-[11px] text-app-muted">
                Nowy podfolder odziedziczy dostęp folderu nadrzędnego:
              </p>
              {inheritedPerms.length === 0 ? (
                <p className="text-[11px] text-app-muted">Brak ról z dostępem (poza administratorem).</p>
              ) : (
                <ul className="divide-y divide-app-line rounded-ctl border border-app-line text-[13px] text-app-text">
                  {inheritedPerms.map((p) => (
                    <li key={p.role} className="px-3 py-1.5">
                      {roleLabel(roles, p.role)}
                      <span className="text-app-muted"> · {ACCESS_LABELS[p.access_level] || p.access_level}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-1 text-[11px] text-app-muted">
                Dostęp dziedziczony jest tylko do wglądu. Zmienisz go później ikoną kłódki na folderze.
              </p>
            </div>
          )}
        </Modal>
      )}

      {permFolder && isAdmin && (
        <Modal title="Uprawnienia folderu" size="lg" onClose={() => setPermFolder(null)}>
          <p className="mb-3 text-[13px] text-app-text">
            Folder: <strong>{permFolder.name}</strong>{' '}
            <span className="text-app-muted">({permFolder.path})</span>
          </p>
          <p className="mb-4 text-[11px] leading-relaxed text-app-muted">
            Rola z uprawnieniem widzi pliki w tym folderze <strong>i jego podfolderach</strong>.
            Uprawnienia oznaczone jako dziedziczone pochodzą z folderu nadrzędnego — zmienisz je
            na tamtym folderze. Administrator ma zawsze pełny dostęp; pliki w katalogu głównym
            widzi tylko administrator.
          </p>

          <div className="mb-4">
            {permLoading ? (
              <div className="py-3 text-[13px] text-app-muted">Ładowanie…</div>
            ) : permEffective.length === 0 ? (
              <div className="rounded-ctl border border-dashed border-app-line py-3 text-center text-[13px] text-app-muted">
                Brak uprawnień — tylko administrator widzi ten folder.
              </div>
            ) : (
              <ul className="divide-y divide-app-line rounded-ctl border border-app-line">
                {permEffective.map((eff) => {
                  // Własne rozszerzenie = bezpośrednie uprawnienie WYŻSZE niż dziedziczone.
                  // Bezpośrednie ≤ dziedziczone jest zdominowane → traktujemy jak dziedziczone.
                  const direct = permissions.find((p) => p.role === eff.role);
                  const isOwn =
                    !!direct && accessRank(direct.access_level) > accessRank(permInhByRole[eff.role]);
                  return (
                    <li key={eff.role} className="flex items-center justify-between gap-3 px-3 py-2 text-[13px]">
                      <span className="text-app-text">
                        {roleLabel(roles, eff.role)}
                        <span className="text-app-muted"> · {ACCESS_LABELS[eff.access_level] || eff.access_level}</span>
                        {!isOwn && (
                          <span className="ml-2 text-[11px] text-app-muted">(dziedziczone z nadrzędnego)</span>
                        )}
                      </span>
                      {isOwn && direct ? (
                        <button
                          onClick={() => handleDeletePermission(direct.id)}
                          className="text-[11px] font-bold text-app-danger hover:underline"
                        >
                          Usuń
                        </button>
                      ) : (
                        <span className="text-[11px] text-app-line">—</span>
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
            <div className="border-t border-app-line pt-4 text-[11px] text-app-muted">
              Wszystkie role mają już maksymalny dostęp (Zapis) — dziedziczony albo własny.
              Nie ma czego dodać.
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2 border-t border-app-line pt-4">
              <div className="min-w-[160px] flex-1">
                <Field label="Rola">
                  <select value={newPermRole} onChange={(e) => setNewPermRole(e.target.value)} className={inputClass}>
                    {permAvailableRoles.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </Field>
              </div>
              <div>
                <Field label="Poziom">
                  <select value={newPermAccess} onChange={(e) => setNewPermAccess(e.target.value)} className={`${inputClass} w-auto`}>
                    {permAvailableLevels.map((lvl) => (
                      <option key={lvl} value={lvl}>{ACCESS_LABELS[lvl]}</option>
                    ))}
                  </select>
                </Field>
              </div>
              <Button variant="primary" onClick={handleAddPermission}>Dodaj</Button>
            </div>
          )}
        </Modal>
      )}

      {showUploadModal && canWriteHere && (
        <Modal
          title="Prześlij pliki"
          onClose={() => { setShowUploadModal(false); setUploadItems([]); }}
          footer={
            <Button onClick={() => { setShowUploadModal(false); setUploadItems([]); }} disabled={uploading}>
              {uploading ? 'Wgrywanie…' : uploadItems.length > 0 ? 'Zamknij' : 'Anuluj'}
            </Button>
          }
        >
          <p className="mb-1 text-[13px] text-app-muted">
            Dozwolone typy: {allowedExts.map((e) => e.toUpperCase()).join(', ')} (do 100 MB).
            Możesz wybrać wiele plików naraz.
          </p>
          <p className="mb-4 text-[13px] text-app-muted">
            Folder docelowy: <strong className="text-app-text">{currentFolderName || 'katalog główny'}</strong>
          </p>
          <input
            type="file"
            multiple
            accept={allowedExts.map((e) => `.${e}`).join(',')}
            onChange={handleUpload}
            className="w-full rounded-ctl border border-app-line p-2 text-[13px]"
            disabled={uploading}
          />

          {uploadItems.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-[13px] font-medium text-app-text">
                Postęp: {uploadItems.filter((it) => it.status === 'done').length}/{uploadItems.length} wgranych
                {uploadItems.some((it) => it.status === 'error') && (
                  <span className="text-app-danger">
                    {' '}({uploadItems.filter((it) => it.status === 'error').length} z błędem)
                  </span>
                )}
              </div>
              <ul className="max-h-48 divide-y divide-app-line overflow-y-auto rounded-ctl border border-app-line">
                {uploadItems.map((it, idx) => (
                  <li key={idx} className="flex items-start gap-2 px-3 py-2 text-[13px]">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STAN_WGRYWANIA[it.status]}`} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-app-text" title={it.name}>{it.name}</span>
                      <span className="block text-[11px] text-app-muted">{OPIS_WGRYWANIA[it.status]}</span>
                      {it.status === 'error' && it.error && (
                        <span className="block text-[11px] text-app-danger">{it.error}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Modal>
      )}

      {selectedFile && (
        <Modal
          size="xl"
          onClose={() => setSelectedFile(null)}
          title={
            <span className="flex items-center gap-2.5">
              <FileTypeIcon filename={selectedFile.filename} size={30} />
              <span className="min-w-0 break-words">{selectedFile.filename}</span>
            </span>
          }
          footer={
            <>
              {(isAdmin || canWriteHere) && (
                <Button variant="danger" onClick={() => { handleDelete(selectedFile.id); setSelectedFile(null); }}>
                  <IconTrash size={16} />
                  Usuń
                </Button>
              )}
              {selectedFile.mime_type === 'application/pdf' && (
                <Button onClick={() => handlePreview(selectedFile)}>
                  <IconEye size={16} />
                  Podgląd
                </Button>
              )}
              <Button variant="primary" onClick={() => handleDownload(selectedFile)}>
                <IconDownload size={16} />
                Pobierz plik
              </Button>
            </>
          }
        >
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Szczegol etykieta="Typ pliku" wartosc={selectedFile.mime_type || 'nieznany'} />
            <Szczegol etykieta="Rozmiar" wartosc={rozmiarPliku(selectedFile.size)} />
            <Szczegol etykieta="Status przetwarzania" wartosc={selectedFile.status} />
            <Szczegol
              etykieta="Data dodania"
              wartosc={czasLokalny(selectedFile.created_at, { dateStyle: 'long', timeStyle: 'short' })}
            />
            <Szczegol etykieta="Folder" wartosc={selectedFile.folder?.path || 'katalog główny'} />
            <Szczegol etykieta="Wczytał" wartosc={selectedFile.uploader?.username || '—'} />
            <Szczegol etykieta="Kategoria" wartosc={etykietaKategorii(selectedFile.doc_type)} />
            {selectedFile.original_filename && selectedFile.original_filename !== selectedFile.filename && (
              <Szczegol etykieta="Nazwa pierwotna" wartosc={selectedFile.original_filename} />
            )}
          </dl>
        </Modal>
      )}

      {renameFolder && (
        <Modal
          title="Zmień nazwę folderu"
          onClose={() => setRenameFolder(null)}
          footer={
            <>
              <Button onClick={() => setRenameFolder(null)}>Anuluj</Button>
              <Button
                variant="primary"
                onClick={submitRename}
                disabled={renaming || !renameValue.trim() || renameValue.trim() === renameFolder.name}
              >
                {renaming ? 'Zapisywanie…' : 'Zapisz'}
              </Button>
            </>
          }
        >
          <Field label="Nazwa folderu">
            <input
              type="text"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitRename(); }}
              autoFocus
              className={inputClass}
            />
          </Field>
          <p className="mt-2 text-[11px] text-app-muted">
            {(() => {
              const subs = folders.filter((f) => f.path.startsWith(renameFolder.path + '/')).length;
              return `Zmiana obejmie ścieżkę tego folderu${subs > 0 ? ` oraz ${subs} podfolderów` : ''}. Pliki i uprawnienia pozostają przypisane bez zmian.`;
            })()}
          </p>
        </Modal>
      )}

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
        <Modal
          title={`Przenieś ${moveTarget.length === 1 ? 'plik' : `pliki (${moveTarget.length})`}`}
          onClose={() => setMoveTarget(null)}
          footer={
            <>
              <Button onClick={() => setMoveTarget(null)}>Anuluj</Button>
              <Button variant="primary" onClick={submitMove} disabled={moving || (!isAdmin && moveFolderId === '')}>
                {moving ? 'Przenoszenie…' : 'Przenieś'}
              </Button>
            </>
          }
        >
          <Field label="Folder docelowy" hint="Widoczne są tylko foldery z prawem zapisu.">
            <select value={moveFolderId} onChange={(e) => setMoveFolderId(e.target.value)} className={inputClass}>
              <option value="">{isAdmin ? '— katalog główny —' : '— wybierz folder —'}</option>
              {folders
                .filter((f) => (isAdmin || f.can_write) && f.id !== currentFolderId)
                // Alfabetycznie po SCIEZCE, nie po nazwie: etykieta pozycji to pelna
                // sciezka, wiec sortowanie po niej ustawia podfoldery pod ich
                // rodzicami. Bez tego lista szla w kolejnosci drzewa, ktora dla
                // szukajacego wyglada jak przypadkowa. `localeCompare` z 'pl',
                // bo zwykle porownanie kodow znakow wypycha slowa z ogonkami na koniec.
                .sort((a, b) => a.path.localeCompare(b.path, 'pl', { numeric: true }))
                .map((f) => (
                  <option key={f.id} value={String(f.id)}>{f.path}</option>
                ))}
            </select>
          </Field>
        </Modal>
      )}
    </div>
  );
}

/** Przełącznik Lista/Kafelki — ten sam dla plików i dla folderów.
 *
 * Stan zaznaczamy jasnym tłem, nie niebieskim wypełnieniem: w tym layoucie
 * niebieski jest kolorem AKCJI, a wybrany widok to stan, nie czynność.
 */
function WidokToggle({
  wartosc, zmien, etykieta,
}: {
  wartosc: ViewMode;
  zmien: (v: ViewMode) => void;
  etykieta: string;
}) {
  return (
    <div className="flex shrink-0 overflow-hidden rounded-ctl border border-app-line" role="group" aria-label={etykieta}>
      {([['list', 'Lista', IconList], ['grid', 'Kafelki', IconGrid]] as const).map(([tryb, opis, Ikona]) => (
        <button
          key={tryb}
          onClick={() => zmien(tryb)}
          aria-pressed={wartosc === tryb}
          className={`flex items-center gap-1.5 px-3 py-2 text-[12px] ${
            wartosc === tryb ? 'bg-[#edf4ff] font-bold text-app-blue' : 'bg-white text-app-text hover:bg-app-hover'
          }`}
        >
          <Ikona size={15} />
          {opis}
        </button>
      ))}
    </div>
  );
}

/** Trzy akcje administratora na folderze — te same w kafelku i w wierszu tabeli.
 *  `stopPropagation`, bo oba pojemniki reagują na kliknięcie wejściem do folderu. */
function AkcjeFolderu({
  folder, zmienNazwe, uprawnienia, usun,
}: {
  folder: Folder;
  zmienNazwe: (f: Folder) => void;
  uprawnienia: (f: Folder) => void;
  usun: (id: number) => void;
}) {
  const klik = (akcja: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    akcja();
  };
  return (
    <>
      <IconButton tone="edit" title="Zmień nazwę folderu" onClick={klik(() => zmienNazwe(folder))}>
        <IconEdit size={16} />
      </IconButton>
      <IconButton tone="lock" title="Uprawnienia folderu" onClick={klik(() => uprawnienia(folder))}>
        <IconLock size={16} />
      </IconButton>
      <IconButton tone="danger" title="Usuń folder" onClick={klik(() => usun(folder.id))}>
        <IconTrash size={16} />
      </IconButton>
    </>
  );
}

/** Jedna pozycja w oknie szczegółów pliku. */
function Szczegol({ etykieta, wartosc }: { etykieta: string; wartosc: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-[.02em] text-app-muted">{etykieta}</dt>
      <dd className="mt-0.5 break-words text-[13px] text-app-text">{wartosc}</dd>
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