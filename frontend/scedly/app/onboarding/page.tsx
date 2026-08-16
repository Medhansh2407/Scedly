'use client';
import { useEffect, useRef } from 'react';
import { useSession } from '@/lib/hooks/useSession';
import { apiFetch } from '@/lib/api';

export default function OnboardingPage() {
  const { token } = useSession();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('/onboarding-static.html')
      .then(r => r.text())
      .then(html => {
        const body = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
        if (ref.current && body) {
          ref.current.innerHTML = body[1]
            .replace(/href="index\.html"/g, 'href="/"')
            .replace(/href="app\.html"/g, 'href="/app"');

          // Wire theme toggle
          ref.current.querySelectorAll('[data-theme-toggle]').forEach(el => {
            el.addEventListener('click', () => {
              const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
              document.documentElement.setAttribute('data-theme', next);
              localStorage.setItem('scedly-theme', next);
            });
          });

          // Wire "Finish setup" to save preferences
          const finishBtn = ref.current.querySelector('.btn-primary');
          if (finishBtn) {
            finishBtn.addEventListener('click', async (e) => {
              if (!token) return;
              e.preventDefault();
              try {
                await apiFetch('/preferences/onboarding-complete', token, { method: 'PUT' });
              } catch {}
              window.location.href = '/app';
            });
          }
        }
      });
  }, [token]);

  return (
    <>
      {/* eslint-disable-next-line @next/next/no-css-tags */}
      <link rel="stylesheet" href="/styles.css" />
      {/* eslint-disable-next-line @next/next/no-css-tags */}
      <link rel="stylesheet" href="/app.css" />
      <div ref={ref} data-theme="dark" />
    </>
  );
}
