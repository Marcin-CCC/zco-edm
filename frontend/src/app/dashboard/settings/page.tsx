'use client';

/** Ustawienia aplikacji (layout 1.5).
 *
 * Trzy sekcje: identyfikacja instancji, integracje i sesja, poczta wychodząca.
 *
 * Identyfikacja to zmiana architektoniczna, nie kosmetyczna: do 1.2.0 nazwa,
 * kolor i ikona pochodziły ze zmiennych środowiskowych ustawianych przy wdrożeniu
 * w trzech miejscach naraz (CI + dwa pliki compose). Raz się to zemściło — ZCO
 * pokazało ikonę HiRS. Teraz wartości siedzą w bazie i zmienia je administrator.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { IconClose } from '@/components/icons';
import { useMarka } from '@/components/marka-provider';
import { Logo } from '@/components/shell/logo';
import {
  Button,
  Card,
  CardHeader,
  Field,
  PageHeader,
  inputClass,
} from '@/components/ui/primitives';
import { settingsApi } from '@/lib/api';

/** Kontrast napisu na tle menu (WCAG 2.1). Poniżej 4,5:1 nazwa robi się trudna
 * do odczytania — ostrzegamy, ale nie blokujemy: to decyzja właściciela marki. */
const TLO_MENU = '#0b2d61';

function luminancja(hex: string): number | null {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const kanaly = [0, 2, 4].map((i) => {
    const v = parseInt(h.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * kanaly[0] + 0.7152 * kanaly[1] + 0.0722 * kanaly[2];
}

function kontrast(a: string, b: string): number | null {
  const la = luminancja(a);
  const lb = luminancja(b);
  if (la === null || lb === null) return null;
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const PROBKI = ['#ffffff', '#1fc8ba', '#7cc4ff', '#ffd166', '#b9c6da'];

export default function SettingsPage() {
  const t = useTranslations('settings');
  const marka = useMarka();
  const [dane, setDane] = useState<any>(null);
  const [form, setForm] = useState({
    app_name: '',
    app_name_color: '',
    n8n_webhook_url: '',
    chat_webhook_url: '',
    allowed_extensions: '',
    idle_timeout_minutes: '15',
    smtp_host: '',
    smtp_port: '587',
    smtp_user: '',
    smtp_password: '',
    smtp_from: '',
    support_email: '',
  });
  const [ikona, setIkona] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [komunikat, setKomunikat] = useState('');
  const [blad, setBlad] = useState('');
  const wybor = useRef<HTMLInputElement>(null);

  const wczytaj = async () => {
    try {
      const d = await settingsApi.get();
      setDane(d);
      setIkona(d.app_icon || '');
      setForm((f) => ({
        ...f,
        app_name: d.app_name || '',
        app_name_color: d.app_name_color || '#ffffff',
        n8n_webhook_url: d.n8n_webhook_url || '',
        chat_webhook_url: d.chat_webhook_url || '',
        allowed_extensions: d.allowed_extensions || '',
        idle_timeout_minutes: String(d.idle_timeout_minutes ?? 15),
        smtp_host: d.smtp_host || '',
        smtp_port: d.smtp_port || '587',
        smtp_user: d.smtp_user || '',
        smtp_password: '',            // hasła backend nie zwraca — puste = bez zmiany
        smtp_from: d.smtp_from || '',
        support_email: d.support_email || '',
      }));
    } catch {
      setBlad(t('errLoad'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { wczytaj(); }, []);

  const zapisz = async () => {
    setSaving(true);
    setBlad('');
    setKomunikat('');
    try {
      // Zapisujemy tylko pola z wartością: pusty klucz backend odrzuca, a puste
      // hasło SMTP ma oznaczać „zostaw dotychczasowe", nie „wyczyść".
      for (const [klucz, wartosc] of Object.entries(form)) {
        if (String(wartosc).trim() === '') continue;
        await settingsApi.updateKey(klucz, wartosc);
      }
      setKomunikat('Ustawienia zapisane.');
      await wczytaj();
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : t('errSave'));
    } finally {
      setSaving(false);
    }
  };

  const wgrajIkone = async (plik?: File | null) => {
    if (!plik) return;
    setBlad('');
    setKomunikat('');
    try {
      const wynik = await settingsApi.uploadAppIcon(plik);
      setIkona(wynik.app_icon);
      setKomunikat(t('iconSaved'));
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : t('errIcon'));
    }
  };

  if (loading) return <div className="text-app-muted">{t('loading')}</div>;

  const wsp = kontrast(form.app_name_color, TLO_MENU);
  const slabyKontrast = wsp !== null && wsp < 4.5;

  return (
    <div className="max-w-3xl">
      <PageHeader title={t('title')} description={t('description')} />

      {komunikat && (
        <div className="mb-4 rounded-ctl border border-[#bfe6d2] bg-app-greenbg px-4 py-3 text-sm text-[#148a57]">
          {komunikat}
        </div>
      )}
      {blad && (
        <div className="mb-4 rounded-ctl border border-[#fecdd3] bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {blad}
        </div>
      )}

      {/* ---------------------------------------------- identyfikacja */}
      <Card className="mb-5">
        <CardHeader><h2 className="text-[15px] font-bold text-app-text">{t('identity')}</h2></CardHeader>
        <div className="space-y-5 p-[18px]">
          <div>
            <span className="mb-1 block text-[13px] font-medium text-app-text">{t('appIcon')}</span>
            <div className="flex flex-wrap items-center gap-3">
              {/* Ciemne tło nie jest ozdobą: ikona bywa biała i na białej karcie
                  byłaby niewidoczna, a i tak trafia na ciemne menu. Pokazujemy
                  ikonę FAKTYCZNIE używaną — gdy własnej nie wgrano, tę wbudowaną.
                  Że jest domyślna, widać po wyszarzonym przycisku obok. */}
              <span className="grid h-12 w-12 flex-none place-items-center overflow-hidden rounded-[9px] bg-app-navy">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={ikona || marka.ikona} alt="" className="h-9 w-9 object-contain" />
              </span>
              <input
                ref={wybor}
                type="file"
                accept=".png,.svg,image/png,image/svg+xml"
                className="hidden"
                onChange={(e) => wgrajIkone(e.target.files?.[0])}
              />
              <Button onClick={() => wybor.current?.click()}>{t('pickFile')}</Button>
              <Button
                onClick={async () => { await settingsApi.resetAppIcon(); setIkona(''); setKomunikat(t('iconRestored')); }}
                disabled={!ikona}
              >
                {t('restoreDefault')}
              </Button>
            </div>
            <p className="mt-1 text-[11px] text-app-muted">
              {t('iconHint')}
            </p>
          </div>

          <Field label={t('appName')} hint={t('appNameHint')}>
            <input
              value={form.app_name}
              onChange={(e) => setForm({ ...form, app_name: e.target.value })}
              maxLength={40}
              className={inputClass}
            />
          </Field>

          <div>
            <span className="mb-1 block text-[13px] font-medium text-app-text">{t('nameColor')}</span>
            <div className="flex flex-wrap items-center gap-2">
              {PROBKI.map((p) => (
                <button
                  key={p}
                  onClick={() => setForm({ ...form, app_name_color: p })}
                  title={p}
                  aria-label={`Kolor ${p}`}
                  className={`h-8 w-8 rounded-lg border ${
                    form.app_name_color.toLowerCase() === p ? 'border-app-text ring-2 ring-app-blue' : 'border-app-line'
                  }`}
                  style={{ background: p }}
                />
              ))}
              <input
                value={form.app_name_color}
                onChange={(e) => setForm({ ...form, app_name_color: e.target.value })}
                placeholder="#ffffff"
                className={`${inputClass} w-32 font-mono`}
              />
            </div>
            {slabyKontrast && (
              <p className="mt-1.5 text-[11px] text-[#b7791f]">
                Niski kontrast na tle menu ({wsp?.toFixed(1)}:1) — napis może być słabo czytelny.
              </p>
            )}
            <p className="mt-1 text-[11px] text-app-muted">
              {t('nameColorHint')}
            </p>
          </div>

          <div>
            <span className="mb-1 block text-[13px] font-medium text-app-text">{t('preview')}</span>
            {/* Podglad rysuje ten sam komponent co pasek boczny — podglad pokazujacy
                cos innego niz aplikacja jest gorszy niz brak podgladu. Gdy wlasnej
                ikony nie wgrano, pokazujemy te, ktora instancja realnie uzywa. */}
            <div className="inline-flex rounded-[9px] px-3 py-2.5" style={{ background: 'var(--app-sidebar)' }}>
              <Logo
                ikona={ikona || marka.ikona}
                nazwa={form.app_name || marka.nazwa}
                kolorNazwy={form.app_name_color || marka.naglowek}
                rozmiarNazwy={22}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* ---------------------------------------- integracje i sesja */}
      <Card className="mb-5">
        <CardHeader><h2 className="text-[15px] font-bold text-app-text">{t('integrations')}</h2></CardHeader>
        <div className="space-y-4 p-[18px]">
          <Field label={t('parseWebhook')}>
            <input
              value={form.n8n_webhook_url}
              onChange={(e) => setForm({ ...form, n8n_webhook_url: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field
            label={t('chatWebhook')}
            hint={t('chatWebhookHint')}
          >
            <input
              value={form.chat_webhook_url}
              onChange={(e) => setForm({ ...form, chat_webhook_url: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field
            label={t('allowedExtensions')}
            hint={t('extensionsHint')}
          >
            <input
              value={form.allowed_extensions}
              onChange={(e) => setForm({ ...form, allowed_extensions: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field
            label={t('idleLogout')}
            hint={t('idleHint')}
          >
            <input
              type="number"
              min={1}
              value={form.idle_timeout_minutes}
              onChange={(e) => setForm({ ...form, idle_timeout_minutes: e.target.value })}
              className={`${inputClass} w-32`}
            />
          </Field>
        </div>
      </Card>

      {/* ------------------------------------------ poczta wychodząca */}
      <Card className="mb-5">
        <CardHeader>
          <h2 className="text-[15px] font-bold text-app-text">{t('mail')}</h2>
          <span className="text-[11px] text-app-muted">
            {t('mailHint')}
          </span>
        </CardHeader>
        <div className="grid grid-cols-1 gap-4 p-[18px] md:grid-cols-2">
          <Field label={t('smtpHost')}>
            <input value={form.smtp_host} onChange={(e) => setForm({ ...form, smtp_host: e.target.value })} placeholder="smtp.firma.pl" className={inputClass} />
          </Field>
          <Field label={t('smtpPort')} hint={t('smtpPortHint')}>
            <input value={form.smtp_port} onChange={(e) => setForm({ ...form, smtp_port: e.target.value })} className={inputClass} />
          </Field>
          <Field label={t('smtpUser')}>
            <input value={form.smtp_user} onChange={(e) => setForm({ ...form, smtp_user: e.target.value })} autoComplete="off" className={inputClass} />
          </Field>
          <Field
            label={t('smtpPassword')}
            hint={dane?.smtp_password_set ? t('smtpPasswordSet') : t('smtpPasswordUnset')}
          >
            <input
              type="password"
              value={form.smtp_password}
              onChange={(e) => setForm({ ...form, smtp_password: e.target.value })}
              autoComplete="new-password"
              className={inputClass}
            />
          </Field>
          <Field label={t('mailFrom')}>
            <input value={form.smtp_from} onChange={(e) => setForm({ ...form, smtp_from: e.target.value })} placeholder="system@firma.pl" className={inputClass} />
          </Field>
          <Field label={t('mailSupport')}>
            <input value={form.support_email} onChange={(e) => setForm({ ...form, support_email: e.target.value })} placeholder="wsparcie@firma.pl" className={inputClass} />
          </Field>
        </div>
      </Card>

      <div className="flex justify-end gap-2">
        <Button onClick={() => { setKomunikat(''); setBlad(''); wczytaj(); }}>
          <IconClose size={16} />
          {t('discard')}
        </Button>
        <Button variant="primary" onClick={zapisz} disabled={saving}>
          {saving ? 'Zapisywanie…' : 'Zapisz ustawienia'}
        </Button>
      </div>
    </div>
  );
}
