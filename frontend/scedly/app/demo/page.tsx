'use client';

import Link from 'next/link';
import { useState } from 'react';
import CalendarToolbar, { CalendarView } from '@/components/CalendarArea/CalendarToolbar';
import DayView from '@/components/CalendarArea/DayView';
import WeekView from '@/components/CalendarArea/WeekView';
import MonthView from '@/components/CalendarArea/MonthView';
import { CalendarEvent } from '@/components/CalendarArea/EventBlock';
import ChatSidebar from '@/components/ChatSidebar/ChatSidebar';
import { ChatMsg } from '@/components/ChatSidebar/MessageList';

const DEMO_DATE = new Date('2026-08-18T12:00:00');

function at(hour: number, minute = 0) {
  const date = new Date(DEMO_DATE);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
}

function initialEvents(): CalendarEvent[] {
  return [
    { id: 'launch', title: 'Launch brief', start: at(9), end: at(10, 30), duration_minutes: 90, priority: 'High', energy_level: 'high', status: 'scheduled', category: 'deep_work' },
    { id: 'review', title: 'Design review', start: at(11, 30), end: at(12, 15), duration_minutes: 45, priority: 'Medium', energy_level: 'medium', status: 'scheduled', category: 'meeting' },
    { id: 'admin', title: 'Inbox + admin', start: at(16), end: at(16, 45), duration_minutes: 45, priority: 'Low', energy_level: 'low', status: 'scheduled', category: 'admin' },
  ];
}

const initialMessages: ChatMsg[] = [{ id: 'welcome', role: 'assistant', content: 'Welcome to the guided sandbox. No account or API key is needed. Try one of the example requests below and watch the calendar adapt.' }];

const suggestions = [
  { label: 'Schedule work', prompt: 'Schedule 45 minutes for release notes after lunch' },
  { label: 'Repair the day', prompt: 'The meeting ran long—move my launch brief' },
  { label: 'Partial progress', prompt: 'I finished half of the launch brief' },
  { label: 'Explain placement', prompt: 'Why is the launch brief at 9am?' },
];

export default function DemoPage() {
  const [view, setView] = useState<CalendarView>('day');
  const [currentDate, setCurrentDate] = useState(new Date(DEMO_DATE));
  const [events, setEvents] = useState<CalendarEvent[]>(initialEvents);
  const [messages, setMessages] = useState<ChatMsg[]>(initialMessages);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  function resetDemo() {
    setCurrentDate(new Date(DEMO_DATE));
    setView('day');
    setEvents(initialEvents());
    setMessages(initialMessages);
    setSending(false);
  }

  function navigate(direction: number) {
    setCurrentDate(date => {
      const next = new Date(date);
      if (view === 'day') next.setDate(next.getDate() + direction);
      else if (view === 'week') next.setDate(next.getDate() + direction * 7);
      else next.setMonth(next.getMonth() + direction);
      return next;
    });
  }

  function completeTask(id: string) {
    setEvents(items => items.map(item => item.id === id ? { ...item, status: 'completed' as const } : item));
  }

  function handleSend(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || sending) return;
    setMessages(items => [...items, { id: `user-${Date.now()}`, role: 'user', content: message }]);
    setSending(true);

    window.setTimeout(() => {
      const normalized = message.toLowerCase();
      let response = '';
      if (normalized.includes('release note')) {
        setEvents(items => items.some(item => item.id === 'release-notes') ? items : [...items, { id: 'release-notes', title: 'Release notes', start: at(14), end: at(14, 45), duration_minutes: 45, priority: 'Medium', energy_level: 'medium', status: 'scheduled', category: 'writing' }]);
        response = '✓ Release notes scheduled Tuesday 14:00–14:45. It fits after lunch, avoids the design review, and preserves the lower-energy admin window.';
      } else if (normalized.includes('meeting ran long') || normalized.includes('move my launch')) {
        setEvents(items => items.map(item => item.id === 'launch' ? { ...item, start: at(12, 30), end: at(14) } : item));
        response = '↻ Launch brief moved to 12:30–14:00. The design review stays protected and the brief still finishes before the release-notes block.';
      } else if (normalized.includes('half') || normalized.includes('partial')) {
        setEvents(items => items.filter(item => item.id !== 'launch-continuation').map(item => item.id === 'launch' ? { ...item, title: 'Launch brief · completed half', start: at(9), end: at(9, 45), duration_minutes: 45, status: 'completed' as const } : item).concat({ id: 'launch-continuation', title: 'Launch brief · continuation', start: at(14, 45), end: at(15, 30), duration_minutes: 45, priority: 'High', energy_level: 'high', status: 'scheduled', category: 'deep_work' }));
        response = '½ Saved 45 minutes as completed and created a linked 45-minute continuation at 14:45. Existing rigid events were left untouched.';
      } else if (normalized.includes('why')) {
        response = 'The launch brief is high-energy work, so 09:00 is inside the preferred focus window. It is the earliest conflict-free block that preserves the 11:30 design review.';
      } else {
        response = 'This is a deterministic portfolio sandbox. Try the guided prompts to see scheduling, recovery, partial completion, and placement explanations. The signed-in product handles free-form requests with the live backend.';
      }
      setMessages(items => [...items, { id: `assistant-${Date.now()}`, role: 'assistant', content: response }]);
      setSending(false);
    }, 350);
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      <header className="flex h-[52px] shrink-0 items-center justify-between border-b border-border bg-surface px-4">
        <div className="flex items-center gap-3"><Link href="/" className="font-mono text-[15px] font-semibold text-cyan">🌙 scedly</Link><span className="rounded-full border border-green/25 bg-green/[.08] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.12em] text-green">Guided demo</span></div>
        <div className="flex items-center gap-2"><button type="button" onClick={resetDemo} className="rounded-md border border-border px-3 py-1.5 text-xs text-text-secondary hover:border-border-hover hover:text-white">Reset</button><Link href="/login" className="rounded-md bg-cyan px-3 py-1.5 text-xs font-semibold text-black">Open full app</Link></div>
      </header>
      <div className="border-b border-cyan/15 bg-cyan/[.05] px-4 py-2 text-center text-[11px] text-text-secondary">Safe, scripted product tour · no account, external API, or persistent data</div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <CalendarToolbar currentDate={currentDate} view={view} onViewChange={setView} onPrev={() => navigate(-1)} onNext={() => navigate(1)} onToday={() => setCurrentDate(new Date(DEMO_DATE))} />
          {view === 'day' && <DayView date={currentDate} events={events} onComplete={completeTask} />}
          {view === 'week' && <WeekView date={currentDate} events={events} onComplete={completeTask} />}
          {view === 'month' && <MonthView date={currentDate} events={events} />}
        </div>
        <ChatSidebar messages={messages} onSend={handleSend} sending={sending} open={sidebarOpen} onToggle={() => setSidebarOpen(open => !open)} suggestions={suggestions} title="Guided scheduling demo" />
      </div>
    </div>
  );
}
