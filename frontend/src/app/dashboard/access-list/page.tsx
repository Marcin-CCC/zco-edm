'use client';

/** Lista dostępów — dostęp efektywny każdej roli do folderów (layout 1.5).
 *
 * Logika zarządzania rolami pochodzi z 1.1.0 i zostaje bez zmian: kod roli jest
 * niezmienny, roli systemowej nie da się usunąć, a usunięcie przenosi użytkowników
 * i kasuje uprawnienia w jednej transakcji (zob. app/roles/router.py).
 */
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';

import { IconEdit, IconPlus, IconTrash } from '@/components/icons';
import { RoleDialog, type RoleDialogMode } from '@/components/role-dialogs';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  IconButton,
  PageHeader,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { foldersApi } from '@/lib/api';
import { ROLE_ADMIN, isAdmin as czyAdmin, roleLabel, useRoles, type Role } from '@/lib/roles';
import { useAuth } from '@/lib/store';

interface AccessItem {
  folder_id: number;
  name: string;
  path: string;
  access_level: string;
  source: string; // 'direct' | 'inherited'
}

const ACCESS_LABELS: Record<string, string> = { read: 'Odczyt', write: 'Zapis' };

export default function AccessListPage() {
  const t = useTranslations('access');
  const { user } = useAuth();
  const isAdmin = czyAdmin(user);
  const { roles, refresh: odswiezRole } = useRoles();
  const [data, setData] = useState<Record<string, AccessItem[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [okno, setOkno] = useState<{ mode: RoleDialogMode; role?: Role } | null>(null);
  const [komunikat, setKomunikat] = useState('');

  const wczytajDostepy = useCallback(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }
    foldersApi
      .accessOverview()
      .then((d) => setData(d || {}))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : t('errFetch')))
      .finally(() => setLoading(false));
  }, [isAdmin]);

  useEffect(() => { wczytajDostepy(); }, [wczytajDostepy]);

  // Po zmianie w słowniku odświeżamy TAKŻE zestawienie dostępów: utworzenie roli
  // z kopią uprawnień i usunięcie roli zmieniają je natychmiast, a tabela sprzed
  // operacji byłaby myląca akurat tam, gdzie chodzi o audyt.
  const poZmianie = (tekst: string) => {
    setOkno(null);
    setKomunikat(tekst);
    odswiezRole();
    wczytajDostepy();
  };

  if (!isAdmin) {
    return <div className="text-sm text-app-muted">{t('adminOnly')}</div>;
  }

  // Kolejność ze słownika ról; administratora pomijamy, bo ma pełny dostęp
  // z definicji. Kody obecne w odpowiedzi, a nieznane słownikowi, dokładamy na
  // koniec — lepiej pokazać rolę bez etykiety niż ukryć jej dostępy.
  const kodyZeSlownika = roles.filter((r) => r.code !== ROLE_ADMIN).map((r) => r.code);
  const kody = [...kodyZeSlownika, ...Object.keys(data).filter((r) => !kodyZeSlownika.includes(r))];

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Button variant="primary" onClick={() => { setKomunikat(''); setOkno({ mode: 'create' }); }}>
            <IconPlus size={18} />
            {t('addRole')}
          </Button>
        }
      />

      {komunikat && (
        <div className="mb-4 rounded-ctl border border-[#bfe6d2] bg-app-greenbg px-4 py-3 text-sm text-[#148a57]">
          {komunikat}
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-ctl border border-[#fecdd3] bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {error}
        </div>
      )}

      {loading ? (
        <Card><EmptyState title={t('loading')} /></Card>
      ) : (
        <div className="space-y-4">
          {kody.map((kod) => {
            const items = data[kod] || [];
            const rola = roles.find((r) => r.code === kod);
            return (
              <Card key={kod} className="overflow-hidden">
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h2 className="text-[15px] font-bold text-app-text">{roleLabel(roles, kod)}</h2>
                    {rola?.is_system && (
                      <Badge tone="gray">
                        <span title={t('systemRoleTitle')}>
                          {t('systemRole')}
                        </span>
                      </Badge>
                    )}
                    <span className="text-xs text-app-muted">
                      {t('foldersCount', { count: items.length })}
                      {rola ? t('usersCount', { count: rola.users_count }) : ''}
                    </span>
                  </div>
                  {rola && (
                    <div className="flex items-center gap-1.5">
                      <IconButton
                        tone="edit"
                        title={t('rename')}
                        onClick={() => { setKomunikat(''); setOkno({ mode: 'rename', role: rola }); }}
                      >
                        <IconEdit size={16} />
                      </IconButton>
                      {rola.is_system ? (
                        <span className="px-1 text-[11px] text-app-muted">{t('noRemoval')}</span>
                      ) : (
                        <IconButton
                          tone="danger"
                          title={t('deleteRole')}
                          onClick={() => { setKomunikat(''); setOkno({ mode: 'delete', role: rola }); }}
                        >
                          <IconTrash size={16} />
                        </IconButton>
                      )}
                    </div>
                  )}
                </CardHeader>

                {items.length === 0 ? (
                  <EmptyState title={t('noAccess')} />
                ) : (
                  <Table>
                    <thead>
                      <tr>
                        <Th>{t('colFolder')}</Th>
                        <Th>{t('colPath')}</Th>
                        <Th>{t('colLevel')}</Th>
                        <Th>{t('colSource')}</Th>
                        <Th className="text-right" />
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it) => (
                        <tr key={it.folder_id} className="hover:bg-app-hover">
                          <Td className="font-semibold text-app-text">{it.name}</Td>
                          <Td className="text-app-muted">{it.path}</Td>
                          <Td>
                            <Badge tone={it.access_level === 'write' ? 'blue' : 'gray'}>
                              {ACCESS_LABELS[it.access_level] || it.access_level}
                            </Badge>
                          </Td>
                          <Td className="text-app-muted">
                            {it.source === 'inherited' ? t('inherited') : t('direct')}
                          </Td>
                          <Td className="text-right">
                            <Link
                              href={`/dashboard/files?folder=${it.folder_id}`}
                              className="text-xs font-semibold text-app-blue hover:underline"
                            >
                              {t('openInFiles')}
                            </Link>
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {okno && (
        <RoleDialog
          mode={okno.mode}
          role={okno.role}
          roles={roles}
          onClose={() => setOkno(null)}
          onDone={poZmianie}
        />
      )}
    </div>
  );
}
