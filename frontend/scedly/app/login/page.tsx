'use client';
import { createClient } from '@/lib/supabase/client';
import Link from 'next/link';

function signIn(provider: 'google' | 'github') {
  const supabase = createClient();
  supabase.auth.signInWithOAuth({
    provider,
    options: { redirectTo: window.location.origin + '/auth/callback' },
  });
}

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0a0c10] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center">
          <Link href="/" className="inline-flex items-center gap-2.5 justify-center">
            <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#2b3550] to-[#1a2236] grid place-items-center text-sm shadow-[0_0_0_1px_rgba(255,255,255,.06)_inset,0_4px_16px_-6px_#5bb8ff]">🌙</span>
            <span className="font-mono font-bold text-lg text-[#e7edf4]">scedly<span className="text-[#6ee7a0] animate-[blink_1.1s_steps(1)_infinite]">_</span></span>
          </Link>
          <h2 className="mt-6 text-2xl font-bold text-[#e7edf4]">Welcome back, founder.</h2>
          <p className="mt-2 text-[#8b97a8]">Sign in to pick up your schedule where you left off.</p>
        </div>

        {/* Card */}
        <div className="mt-8 bg-[#12161f] border border-[#232a37] rounded-xl p-6 shadow-[0_8px_28px_-8px_rgba(0,0,0,.6)]">
          {/* Terminal flavor */}
          <div className="bg-[#07090d] border border-[#303a4b] rounded-lg overflow-hidden mb-5">
            <div className="px-3.5 py-3 font-mono text-sm leading-relaxed">
              <span className="text-[#6ee7a0] font-bold">scedly&gt;</span> <span className="text-[#e7edf4]">auth login</span><br />
              <span className="text-[#4a6a57]">  authenticating via supabase…</span><br />
              <span className="text-[#5bb8ff]">  choose a provider ↓</span>
            </div>
          </div>

          {/* OAuth buttons */}
          <div className="flex flex-col gap-3">
            <button
              onClick={() => signIn('google')}
              className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-lg border border-[#303a4b] bg-[#1b212e] text-[#e7edf4] font-semibold text-sm hover:border-[#5bb8ff] hover:bg-[#161b26] transition-all"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z"/>
              </svg>
              Continue with Google
            </button>
            <button
              onClick={() => signIn('github')}
              className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-lg border border-[#303a4b] bg-[#1b212e] text-[#e7edf4] font-semibold text-sm hover:border-[#5bb8ff] hover:bg-[#161b26] transition-all"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="currentColor" d="M12 1A11 11 0 0 0 8.52 22.44c.55.1.75-.24.75-.53v-1.86c-3.06.67-3.71-1.47-3.71-1.47-.5-1.28-1.22-1.62-1.22-1.62-1-.68.08-.67.08-.67 1.1.08 1.69 1.14 1.69 1.14.98 1.68 2.57 1.2 3.2.92.1-.71.38-1.2.69-1.47-2.44-.28-5.01-1.22-5.01-5.44 0-1.2.43-2.18 1.13-2.95-.11-.28-.49-1.4.11-2.92 0 0 .93-.3 3.05 1.13a10.6 10.6 0 0 1 5.56 0c2.12-1.43 3.04-1.13 3.04-1.13.6 1.52.22 2.64.11 2.92.7.77 1.13 1.75 1.13 2.95 0 4.23-2.58 5.16-5.03 5.43.4.34.74 1 .74 2.02v3c0 .29.2.64.76.53A11 11 0 0 0 12 1z"/>
              </svg>
              Continue with GitHub
            </button>
          </div>

          <p className="text-center mt-6 font-mono text-xs text-[#5c6675]">
            We only request your email. No passwords, ever.
          </p>
        </div>

        <p className="text-center mt-6 text-sm text-[#8b97a8]">
          New here? Signing in creates your account.<br />
          By continuing you agree to the Terms & Privacy Policy.
        </p>
      </div>
    </div>
  );
}
