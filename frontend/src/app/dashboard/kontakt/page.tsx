'use client';

/** Skontaktuj się — zgłoszenie do wsparcia technicznego.
 *
 * Wysyłkę robi backend własnym SMTP-em (app/contact.py), a nie n8n: awaria n8n
 * nie może odcinać drogi zgłoszenia problemu, bo wtedy zgłoszenia są najbardziej
 * potrzebne. Gdy poczta nie jest skonfigurowana, backend odpowiada 503 z jasną
 * przyczyną — użytkownik ma wiedzieć, że wiadomość NIE poszła, zamiast zobaczyć
 * potwierdzenie wysyłki, której nie było.
 */
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useState } from 'react';

import { Button, Card, Field, PageHeader, inputClass } from '@/components/ui/primitives';
import { contactApi } from '@/lib/api';
import { useAuth } from '@/lib/store';

const MIN_ZNAKOW = 10;

export default function KontaktPage() {
  const t = useTranslations('contact');
  const tWspolne = useTranslations('common');
  const { user } = useAuth();
  const router = useRouter();
  const [tresc, setTresc] = useState('');
  const [wysylanie, setWysylanie] = useState(false);
  const [wyslano, setWyslano] = useState('');
  const [blad, setBlad] = useState('');

  const zaKrotkie = tresc.trim().length < MIN_ZNAKOW;

  async function wyslij() {
    setWysylanie(true);
    setBlad('');
    try {
      const wynik = await contactApi.send(tresc.trim());
      setWyslano(t('sent', { adres: wynik.do }));
      setTresc('');
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : t('errSend'));
    } finally {
      setWysylanie(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader
        title={t('title')}
        description={t('description')}
      />

      {wyslano && (
        <div className="mb-4 rounded-ctl border border-[#bfe6d2] bg-app-greenbg px-4 py-3 text-sm text-[#148a57]">
          {wyslano}
        </div>
      )}
      {blad && (
        <div className="mb-4 rounded-ctl border border-[#fecdd3] bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {blad}
        </div>
      )}

      <Card className="p-[18px]">
        <div className="mb-4">
          <Field label={t('reporter')}>
            <input
              value={`${user?.full_name || user?.username || ''}${user?.email ? ` · ${user.email}` : ''}`}
              readOnly
              className={`${inputClass} bg-app-bg text-app-muted`}
            />
          </Field>
        </div>

        <Field label={t('body')}>
          <textarea
            value={tresc}
            onChange={(e) => setTresc(e.target.value)}
            rows={8}
            maxLength={5000}
            placeholder={t('bodyPlaceholder')}
            className={`${inputClass} h-auto py-2.5`}
          />
        </Field>
        <p className="mt-1 text-[11px] text-app-muted">
          {tresc.trim().length}/5000 znaków{zaKrotkie && tresc.length > 0 ? ` — jeszcze ${MIN_ZNAKOW - tresc.trim().length}` : ''}
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={() => router.back()}>{tWspolne('cancel')}</Button>
          <Button variant="primary" onClick={wyslij} disabled={wysylanie || zaKrotkie}>
            {wysylanie ? t('sending') : t('send')}
          </Button>
        </div>
      </Card>
    </div>
  );
}
