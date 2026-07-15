'use client';
import { useEffect, useRef, useState } from 'react';
import { useSession } from '@/lib/hooks/useSession';
import { apiFetch } from '@/lib/api';

function showKeyModal(key: string, name: string) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;display:grid;place-items:center;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px)';
  overlay.innerHTML = `
    <div style="background:#12161f;border:1px solid #303a4b;border-radius:12px;padding:32px;max-width:520px;width:90%;box-shadow:0 24px 60px -16px rgba(0,0,0,.7)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-size:20px">🔑</span>
        <h2 style="font-family:'JetBrains Mono',monospace;font-size:1.1rem;font-weight:700;color:#e7edf4;margin:0">Key created: ${name}</h2>
      </div>
      <p style="color:#8b97a8;font-size:.85rem;margin:8px 0 20px">This key will <strong style="color:#ef5350">never be shown again</strong>. Copy it now and store it safely.</p>
      <div style="background:#07090d;border:1px solid #303a4b;border-radius:8px;padding:14px 16px;display:flex;align-items:center;gap:12px">
        <code style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#6ee7a0;word-break:break-all;flex:1">${key}</code>
        <button id="copy-key-btn" style="padding:8px 14px;border-radius:8px;border:1px solid #303a4b;background:#1b212e;color:#e7edf4;font-family:'JetBrains Mono',monospace;font-size:.8rem;font-weight:600;cursor:pointer;white-space:nowrap">Copy</button>
      </div>
      <div style="margin-top:10px;background:#07090d;border:1px solid #303a4b;border-radius:8px;padding:10px 16px;font-family:'JetBrains Mono',monospace;font-size:.75rem;color:#4a6a57">
        $ scedly login<br>API key (sk-...): <span style="color:#6ee7a0">paste here</span>
      </div>
      <button id="close-key-modal" style="margin-top:20px;width:100%;padding:10px;border-radius:8px;border:none;background:#5bb8ff;color:#04121f;font-weight:600;font-size:.9rem;cursor:pointer">I've copied my key</button>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#copy-key-btn')!.addEventListener('click', () => {
    navigator.clipboard.writeText(key);
    const btn = overlay.querySelector('#copy-key-btn') as HTMLElement;
    btn.textContent = '✓ Copied';
    btn.style.background = '#4cc38a';
    btn.style.borderColor = '#4cc38a';
    btn.style.color = '#04121f';
  });
  overlay.querySelector('#close-key-modal')!.addEventListener('click', () => {
    overlay.remove();
    window.location.reload();
  });
  overlay.addEventListener('click', (e) => { if (e.target === overlay) { overlay.remove(); window.location.reload(); } });
}

export default function SettingsPage() {
  const { token, loading } = useSession();
  const ref = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    setTheme(localStorage.getItem('scedly-theme') || 'dark');
  }, []);

  useEffect(() => {
    if (!token) return;
    fetch('/settings-static.html')
      .then(r => r.text())
      .then(html => {
        const body = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
        if (ref.current && body) {
          ref.current.innerHTML = body[1]
            .replace(/href="index\.html"/g, 'href="/"')
            .replace(/href="app\.html"/g, 'href="/app"')
            .replace(/href="settings\.html"/g, 'href="/settings"');

          // Wire theme toggle
          ref.current.querySelectorAll('[data-theme-toggle]').forEach(el => {
            el.addEventListener('click', () => {
              const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
              document.documentElement.setAttribute('data-theme', next);
              localStorage.setItem('scedly-theme', next);
            });
          });

          // Wire tab switching
          ref.current.querySelectorAll('[data-tabs]').forEach(group => {
            const tabs = group.querySelectorAll('[data-tab]');
            tabs.forEach(tab => {
              tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const target = tab.getAttribute('data-tab');
                const scope = (group as HTMLElement).getAttribute('data-tabs');
                ref.current?.querySelectorAll(`[data-panel="${scope}"]`).forEach(p => {
                  (p as HTMLElement).style.display = p.getAttribute('data-tab-panel') === target ? '' : 'none';
                });
              });
            });
          });

          // Wire buttons (after DOM is injected)
          ref.current.querySelectorAll('.btn-primary').forEach(btn => {
            const text = btn.textContent || '';
            if (text.includes('Generate new key')) {
              btn.addEventListener('click', async () => {
                const name = prompt('Key name (e.g. "cli", "mcp"):');
                if (!name) return;
                try {
                  const data = await apiFetch('/api-keys', token, { method: 'POST', body: JSON.stringify({ name }) });
                  showKeyModal(data.key, name);
                } catch (e: any) { alert('Failed to create key: ' + e.message); }
              });
            } else if (text.includes('$9/mo')) {
              btn.addEventListener('click', async () => {
                const { url } = await apiFetch('/billing/checkout', token, { method: 'POST', body: JSON.stringify({ interval: 'monthly' }) });
                window.location.href = url;
              });
            } else if (text.includes('$96/yr')) {
              btn.addEventListener('click', async () => {
                const { url } = await apiFetch('/billing/checkout', token, { method: 'POST', body: JSON.stringify({ interval: 'yearly' }) });
                window.location.href = url;
              });
            }
          });
          ref.current.querySelectorAll('.btn-ghost').forEach(btn => {
            if ((btn.textContent || '').includes('billing portal')) {
              btn.addEventListener('click', async () => {
                const { url } = await apiFetch('/billing/portal', token, { method: 'POST' });
                window.location.href = url;
              });
            }
          });

          // Wire integration Connect buttons
          const intgRows = ref.current.querySelectorAll('.btn-outline');
          intgRows.forEach(btn => {
            const row = btn.closest('.set-row');
            const label = row?.querySelector('h4')?.textContent || '';
            btn.addEventListener('click', async () => {
              try {
                let endpoint = '';
                if (label.includes('Google Calendar')) endpoint = '/calendar-sync/google/auth';
                else if (label.includes('Outlook')) endpoint = '/calendar-sync/microsoft/auth';
                else if (label.includes('Telegram')) { alert('Send any message to @ScedlyBot on Telegram. It will give you a linking code to paste here in settings.'); return; }
                else if (label.includes('Slack')) { alert('Slack integration coming soon. Use the web app or CLI for now.'); return; }
                else if (label.includes('Google Chat')) { alert('Google Chat integration coming soon.'); return; }
                if (endpoint) {
                  const data = await apiFetch(endpoint, token);
                  if (data.auth_url) window.location.href = data.auth_url;
                }
              } catch (e: any) { alert('Connection failed: ' + e.message); }
            });
          });

          // Wire timezone select
          const tzSelect = ref.current.querySelector('select.input') as HTMLSelectElement;
          if (tzSelect) {
            // Load current timezone from backend
            apiFetch('/preferences', token).then((prefs: any) => {
              const tz = prefs?.timezone || 'America/New_York';
              for (let i = 0; i < tzSelect.options.length; i++) {
                if (tzSelect.options[i].textContent?.includes(tz) || tzSelect.options[i].value === tz) {
                  tzSelect.selectedIndex = i;
                  break;
                }
              }
            }).catch(() => {});
            // Save on change
            tzSelect.addEventListener('change', async () => {
              const selected = tzSelect.options[tzSelect.selectedIndex].textContent || '';
              const tz = selected.split(' ')[0]; // "America/New_York (GMT-4)" -> "America/New_York"
              try {
                await apiFetch('/preferences/timezone', token, { method: 'PUT', body: JSON.stringify({ timezone: tz }) });
              } catch (e) { console.error('Failed to save timezone', e); }
            });
          }
        }
      });
  }, [token]);

  if (loading) return <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}><span className="mono" style={{ color: 'var(--term-green)' }}>loading...</span></div>;

  return (
    <>
      <link rel="stylesheet" href="/styles.css" />
      <link rel="stylesheet" href="/app.css" />
      <div ref={ref} data-theme={theme} />
    </>
  );
}
