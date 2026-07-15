'use client';
import { useEffect, useState, useCallback } from 'react';
import { useSession } from '@/lib/hooks/useSession';
import { apiFetch, chatStream } from '@/lib/api';
import NavBar from '@/components/NavBar';
import CalendarToolbar, { CalendarView } from '@/components/CalendarArea/CalendarToolbar';
import DayView from '@/components/CalendarArea/DayView';
import WeekView from '@/components/CalendarArea/WeekView';
import MonthView from '@/components/CalendarArea/MonthView';
import { CalendarEvent } from '@/components/CalendarArea/EventBlock';
import ChatSidebar from '@/components/ChatSidebar/ChatSidebar';
import { ChatMsg } from '@/components/ChatSidebar/MessageList';

export default function AppPage() {
  const { user, token, loading } = useSession();
  const [view, setView] = useState<CalendarView>('day');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [messages, setMessages] = useState<ChatMsg[]>([
    { id: 'welcome', role: 'assistant', content: "Hey! I'm Scedly. Tell me what you need to get done and I'll schedule it.\n\nTry: \"schedule a 2h deep work session tomorrow morning\"" }
  ]);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const fetchEvents = useCallback(async () => {
    if (!token) return;
    try { const d = await apiFetch('/calendar', token); setEvents(d.blocks || []); } catch {}
  }, [token]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  useEffect(() => {
    if (!token) return;
    apiFetch('/chat/history?session_id=web&limit=20', token)
      .then((history: { id: string; role: 'user' | 'assistant'; content: string }[]) => {
        if (history.length > 0) {
          setMessages(history.map(m => ({ id: m.id, role: m.role, content: m.content })));
        }
      })
      .catch(() => {});
  }, [token]);

  function nav(dir: number) {
    setCurrentDate(d => {
      const n = new Date(d);
      if (view === 'day') n.setDate(n.getDate() + dir);
      else if (view === 'week') n.setDate(n.getDate() + dir * 7);
      else n.setMonth(n.getMonth() + dir);
      return n;
    });
  }

  async function handleComplete(id: string) {
    if (!token) return;
    try { await apiFetch(`/tasks/${id}/complete`, token, { method: 'POST' }); setEvents(ev => ev.map(e => e.id === id ? { ...e, status: 'completed' } : e)); } catch {}
  }

  async function handleSend(message: string) {
    if (!token) return;
    const aiId = (Date.now() + 1).toString();
    setMessages(m => [...m, { id: Date.now().toString(), role: 'user', content: message }, { id: aiId, role: 'assistant', content: '', streaming: true }]);
    setSending(true);

    const fail = (msg: string) => { setMessages(m => m.map(x => x.id === aiId ? { ...x, content: msg, streaming: false } : x)); setSending(false); };

    let res: Response;
    try { res = await chatStream(message, token); } catch (err: unknown) { return fail(`Could not reach backend: ${err instanceof Error ? err.message : err}`); }
    if (!res.ok) { const t = await res.text().catch(() => ''); return fail(`Backend error ${res.status}: ${t.slice(0, 120)}`); }
    if (!res.body) return fail('No response body.');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let acc = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value, { stream: true }).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') break;
          try { const j = JSON.parse(data); if (j.type === 'token') { acc += j.content; setMessages(m => m.map(x => x.id === aiId ? { ...x, content: acc } : x)); } else if (j.type === 'error') { return fail(`AI error: ${j.message}`); } } catch {}
        }
      }
    } catch { if (!acc) return fail('Stream interrupted.'); }

    setMessages(m => m.map(x => x.id === aiId ? { ...x, streaming: false } : x));
    setSending(false);
    fetchEvents();
  }

  if (loading) return <div className="h-screen flex items-center justify-center bg-bg"><span className="font-mono text-[13px] text-cyan">loading...</span></div>;

  return (
    <div className="h-screen flex flex-col bg-bg overflow-hidden">
      <NavBar displayName={user?.user_metadata?.full_name} avatarUrl={user?.user_metadata?.avatar_url} trialDaysLeft={9} />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">
          <CalendarToolbar currentDate={currentDate} view={view} onViewChange={setView} onPrev={() => nav(-1)} onNext={() => nav(1)} onToday={() => setCurrentDate(new Date())} />
          {view === 'day' && <DayView date={currentDate} events={events} onComplete={handleComplete} />}
          {view === 'week' && <WeekView date={currentDate} events={events} onComplete={handleComplete} />}
          {view === 'month' && <MonthView date={currentDate} events={events} />}
        </div>
        <ChatSidebar messages={messages} onSend={handleSend} sending={sending} open={sidebarOpen} onToggle={() => setSidebarOpen(o => !o)} />
      </div>
    </div>
  );
}
