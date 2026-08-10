# Raport parsowania — pole HTML w węźle „Send an Email"

Przepływ parsowania (`AmcCFLmgvgZKLZP3`), węzeł **Send an Email**, pole **HTML**.
Poniżej cała zawartość pola do podmiany.

## Co się zmieniło wobec poprzedniej wersji

1. **Usunięta linia `Wgrał: {{ … }}` sprzed wyrażenia.** Stała POZA blokiem `{{ }}`,
   więc trafiała przed `<!DOCTYPE html>` — klient pocztowy pokazywał ją jako goły
   tekst nad ramką raportu, bez żadnego stylu.
2. **Autor wgrania w nagłówku**, pod nazwą pliku, w stylu nadlinii „Raport parsowania
   dokumentu" (12 px, wersaliki, szarość `#6b7280`).
3. **Nazwa instancji dopisana do nadlinii** — „RAPORT PARSOWANIA DOKUMENTU · ZCO DM".
   Temat maila i tak dostaje prefiks, ale w przekazanym dalej albo wydrukowanym
   raporcie temat znika, a nadlinia zostaje. Jeśli uznasz to za zbędne, usuń
   fragment `+ (instancja ? ' · ' + esc(instancja) : '')`.
4. **Odczyt pól w `try/catch`.** Gdyby webhook kiedyś ich nie przysłał (stary przebieg,
   zmiana w backendzie), raport ma się wysłać mimo to — z wartością „nieznany".
   Bez tego zabezpieczenia błąd wyrażenia przerwałby wysyłkę CAŁEGO raportu.

Pola `uzytkownik` i `instancja` dokłada backend do payloadu webhooka parsowania
(`app/files/router.py`, `build_webhook_payload`). Pliki wysłane do parsowania przed
wdrożeniem z 2026-08-10 ich nie mają — zadziała zabezpieczenie z punktu 4.

## Temat wiadomości (osobne pole tego samego węzła)

Tryb Expression, przedrostek przed dotychczasową treścią:

```
[{{ $('Webhook').first().json.body.instancja }}] 
```

## Pole HTML — cała zawartość

```
{{
(() => {
  const r = $json;
  const s = r.stats || {};
  const issues = r.issues || [];

  // Autor wgrania i nazwa instancji — z payloadu webhooka parsowania.
  // try/catch, bo brak tych pól nie może przerwać wysyłki raportu.
  let kto = 'nieznany';
  let instancja = '';
  try {
    const body = $('Webhook').first().json.body || {};
    kto = body.uzytkownik || 'nieznany';
    instancja = body.instancja || '';
  } catch (e) { /* starszy przebieg bez tych pól */ }

  // kolory statusu
  const statusColor = { PASS: '#16a34a', REVIEW: '#d97706', FAIL: '#dc2626' }[r.status] || '#6b7280';
  const sevMeta = {
    error:   { label: 'BŁĄD',      color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
    review:  { label: 'DO PRZEGLĄDU', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
    warning: { label: 'OSTRZEŻENIE', color: '#ca8a04', bg: '#fefce8', border: '#fef08a' },
    info:    { label: 'INFO',      color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  };

  const order = ['error', 'review', 'warning', 'info'];
  const sorted = [...issues].sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));

  const esc = (t) => (t == null ? '' : String(t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'));

  const issueRows = sorted.length
    ? sorted.map((i) => {
        const m = sevMeta[i.severity] || sevMeta.info;
        return (
          '<tr>' +
          '<td style="padding:8px 12px;vertical-align:top;white-space:nowrap;">' +
            '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;' +
            'color:' + m.color + ';background:' + m.bg + ';border:1px solid ' + m.border + ';">' + m.label + '</span>' +
          '</td>' +
          '<td style="padding:8px 12px;vertical-align:top;font-size:12px;color:#6b7280;white-space:nowrap;">' + esc(i.type) + '</td>' +
          '<td style="padding:8px 12px;vertical-align:top;font-size:13px;color:#111827;line-height:1.5;">' + esc(i.detail) + '</td>' +
          '</tr>'
        );
      }).join('')
    : '<tr><td colspan="3" style="padding:16px;text-align:center;color:#16a34a;font-size:14px;">Brak zastrzeżeń — dokument sparsowany czysto.</td></tr>';

  const byType = s.by_type || {};
  const typeChips = Object.keys(byType).map((k) =>
    '<span style="display:inline-block;margin:2px 4px 2px 0;padding:3px 10px;border-radius:12px;' +
    'background:#f3f4f6;color:#374151;font-size:12px;">' + esc(k) + ': <b>' + byType[k] + '</b></span>'
  ).join('');

  const statCard = (label, val) =>
    '<td style="padding:12px 16px;text-align:center;border-right:1px solid #e5e7eb;">' +
      '<div style="font-size:22px;font-weight:700;color:#111827;">' + (val ?? 0) + '</div>' +
      '<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.4px;margin-top:2px;">' + label + '</div>' +
    '</td>';

  return (
'<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f9fafb;">' +
'<div style="max-width:640px;margin:0 auto;padding:24px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">' +

  // nagłówek ze statusem
  '<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px 12px 0 0;padding:20px 24px;border-bottom:none;">' +
    '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.6px;">Raport parsowania dokumentu' + (instancja ? ' · ' + esc(instancja) : '') + '</div>' +
    '<div style="font-size:18px;font-weight:600;color:#111827;margin-top:4px;word-break:break-all;">' + esc(r.filename || '—') + '</div>' +
    '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.6px;margin-top:6px;">Wgrał: ' + esc(kto) + '</div>' +
    '<div style="margin-top:12px;">' +
      '<span style="display:inline-block;padding:6px 16px;border-radius:6px;font-size:14px;font-weight:700;color:#ffffff;background:' + statusColor + ';">' +
      'STATUS: ' + esc(r.status || '—') + '</span>' +
    '</div>' +
  '</div>' +

  // pasek statystyk
  '<div style="background:#ffffff;border:1px solid #e5e7eb;border-bottom:none;">' +
    '<table style="width:100%;border-collapse:collapse;"><tr>' +
      statCard('Chunków', s.total_chunks) +
      statCard('Liście', s.hier_leaves) +
      statCard('Sieroty', s.hier_orphans) +
      statCard('Podziały', s.splits) +
      '<td style="padding:12px 16px;text-align:center;">' +
        '<div style="font-size:22px;font-weight:700;color:#111827;">' + (s.flat_rows ?? 0) + '</div>' +
        '<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.4px;margin-top:2px;">Wiersze płaskie</div>' +
      '</td>' +
    '</tr></table>' +
    '<div style="padding:12px 16px;border-top:1px solid #f3f4f6;">' + typeChips + '</div>' +
  '</div>' +

  // tabela issues
  '<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:0 0 12px 12px;padding:4px;">' +
    '<table style="width:100%;border-collapse:collapse;">' +
      '<thead><tr style="border-bottom:2px solid #e5e7eb;">' +
        '<th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;">Waga</th>' +
        '<th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;">Typ</th>' +
        '<th style="padding:10px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;">Szczegóły</th>' +
      '</tr></thead>' +
      '<tbody>' + issueRows + '</tbody>' +
    '</table>' +
  '</div>' +

  '<div style="text-align:center;padding:16px;font-size:11px;color:#9ca3af;">' +
    'Automatyczny raport QA · pipeline parsowania dokumentów' +
  '</div>' +

'</div></body></html>'
  );
})()
}}
```

## Po edycji

Kliknij **Publish** — od n8n 2.34 sam zapis nie wchodzi do ruchu. Weryfikacja:
`versionId` musi być równy `activeVersionId`.
