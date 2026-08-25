'use client';

/** Użytkownicy — konta w systemie, ich role i status dostępu (layout 1.5).
 *
 * Logika bez zmian względem poprzedniej wersji: ten sam formularz obsługuje
 * dodawanie i edycję, hasło przy edycji zostaje puste (puste = bez zmiany),
 * a własnego konta nie da się usunąć. Zmienia się wyłącznie warstwa wizualna.
 */
import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import { IconEdit, IconPlus, IconTrash } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  IconButton,
  PageHeader,
  RowActions,
  Sub,
  Table,
  Td,
  Th,
  inputClass,
} from '@/components/ui/primitives';
import { usersApi } from '@/lib/api';
import { ROLE_GUEST, roleLabel, useRoles } from '@/lib/roles';
import { useAuth } from '@/lib/store';
import { inicjaly } from '@/lib/user';

export default function UsersPage() {
  const t = useTranslations('users');
  const tWspolne = useTranslations('common');
  const { token, user } = useAuth();
  const { roles } = useRoles();
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({
    email: '',
    username: '',
    password: '',
    full_name: '',
    role: ROLE_GUEST,
    is_active: true,
  });

  const fetchUsers = async () => {
    try {
      setUsers(await usersApi.list(token!));
    } catch (err: any) {
      setError(err.message || t('errFetch'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const resetForm = () => {
    setForm({ email: '', username: '', password: '', full_name: '', role: ROLE_GUEST, is_active: true });
    setShowForm(false);
    setEditingId(null);
  };

  const handleEdit = (u: any) => {
    setForm({
      email: u.email || '',
      username: u.username || '',
      password: '',
      full_name: u.full_name || '',
      role: u.role || ROLE_GUEST,
      is_active: u.is_active,
    });
    setEditingId(u.id);
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (editingId) {
        const { password, ...rest } = form;
        const updates: Record<string, unknown> = { ...rest };
        if (password) updates.password = password;   // puste = bez zmiany hasła
        await usersApi.update(token!, editingId, updates);
      } else {
        await usersApi.create(token!, form);
      }
      resetForm();
      fetchUsers();
    } catch (err: any) {
      setError(err.message || t('errSave'));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('confirmDelete'))) return;
    try {
      await usersApi.delete(token!, id);
      fetchUsers();
    } catch (err: any) {
      setError(err.message || t('errDelete'));
    }
  };

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          !showForm && (
            <Button variant="primary" onClick={() => setShowForm(true)}>
              <IconPlus size={18} />
              {t('addUser')}
            </Button>
          )
        }
      />

      {error && (
        <div className="mb-4 rounded-ctl border border-[#fecdd3] bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {error}
        </div>
      )}

      {showForm && (
        <Card className="mb-5 p-[18px]">
          <h2 className="mb-4 text-base font-bold text-app-text">
            {editingId ? t('editUser') : t('addNewUser')}
          </h2>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label={t('colEmail')}>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className={inputClass}
                required
              />
            </Field>
            <Field label={t('displayName')}>
              <input
                type="text"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className={inputClass}
                required
              />
            </Field>
            <Field label={t('password')} hint={editingId ? t('passwordHint') : undefined}>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className={inputClass}
                required={!editingId}
                autoComplete="new-password"
              />
            </Field>
            <Field label={t('fullName')}>
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label={t('colRole')}>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className={inputClass}
              >
                {roles.map((r) => (
                  <option key={r.code} value={r.code}>{r.name}</option>
                ))}
              </select>
            </Field>
            <label className="flex items-center gap-2 pt-7 text-[13px] text-app-text">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                className="rounded border-app-line text-app-blue"
              />
              {t('active')}
            </label>
            <div className="flex justify-end gap-2 md:col-span-2">
              <Button type="button" onClick={resetForm}>{tWspolne('cancel')}</Button>
              <Button type="submit" variant="primary">
                {editingId ? 'Zapisz zmiany' : 'Dodaj'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card className="overflow-hidden">
        {loading ? (
          <EmptyState title={t('loading')} />
        ) : users.length === 0 ? (
          <EmptyState title={t('empty')} hint={t('emptyHint')} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-[280px]">{t('colUser')}</Th>
                <Th>{t('colEmail')}</Th>
                <Th>{t('colRole')}</Th>
                <Th>{t('colStatus')}</Th>
                <Th className="text-right">{t('colActions')}</Th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="group hover:bg-app-hover">
                  <Td>
                    <div className="flex items-center gap-3">
                      <span className="grid h-9 w-9 flex-none place-items-center rounded-full bg-app-blue text-xs font-bold text-white">
                        {inicjaly(u.full_name, u.username)}
                      </span>
                      <span>
                        <span className="font-semibold text-app-text">{u.username}</span>
                        {u.full_name && <Sub>{u.full_name}</Sub>}
                      </span>
                    </div>
                  </Td>
                  <Td className="text-app-muted">{u.email}</Td>
                  <Td><Badge tone="blue">{roleLabel(roles, u.role)}</Badge></Td>
                  <Td>
                    <Badge tone={u.is_active ? 'green' : 'danger'}>
                      {u.is_active ? t('active') : t('inactive')}
                    </Badge>
                  </Td>
                  <Td>
                    <RowActions>
                      <IconButton tone="edit" title={t('edit')} onClick={() => handleEdit(u)}>
                        <IconEdit size={16} />
                      </IconButton>
                      {u.id !== user?.id && (
                        <IconButton tone="danger" title={tWspolne('delete')} onClick={() => handleDelete(u.id)}>
                          <IconTrash size={16} />
                        </IconButton>
                      )}
                    </RowActions>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
