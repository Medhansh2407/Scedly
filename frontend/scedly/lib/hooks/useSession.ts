'use client';
import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import type { User, Session } from '@supabase/supabase-js';

export function useSession() {
  const localDev = process.env.NEXT_PUBLIC_LOCAL_DEV_MODE === 'true';
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(() => localDev ? ({ access_token: 'local-dev-token' } as Session) : null);
  const [loading, setLoading] = useState(!localDev);

  useEffect(() => {
    if (localDev) return;
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session); setUser(data.session?.user ?? null); setLoading(false);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => {
      setSession(s); setUser(s?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, [localDev]);

  return { user, session, loading, token: session?.access_token ?? null };
}
