'use client';

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  duration_minutes: number;
  priority: 'High' | 'Medium' | 'Low' | null;
  energy_level?: string | null;
  status: 'scheduled' | 'in_progress' | 'completed' | 'missed' | 'unscheduled' | null;
  category?: string | null;
}

interface Props {
  event: CalendarEvent;
  style?: React.CSSProperties;
  onComplete?: (id: string) => void;
}

const styles: Record<string, { card: string; border: string }> = {
  High: { card: 'bg-gradient-to-br from-red/[.13] to-red/[.02]', border: 'border-l-red' },
  Medium: { card: 'bg-gradient-to-br from-amber/[.11] to-amber/[.02]', border: 'border-l-amber' },
  Low: { card: 'bg-gradient-to-br from-green/[.11] to-green/[.02]', border: 'border-l-green' },
  break: { card: 'bg-white/[.012]', border: 'border-l-border' },
};

function fmt(iso: string) { return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }); }
function dur(m: number) { return m >= 60 ? `${Math.floor(m/60)}h${m%60 ? m%60+'m':''}` : `${m}m`; }

export default function EventBlock({ event, style, onComplete }: Props) {
  const s = styles[event.category === 'break' ? 'break' : (event.priority || 'Medium')];
  const done = event.status === 'completed';

  return (
    <div style={style} className={`absolute left-2 right-2 rounded-[9px] p-[9px_13px] border border-transparent border-l-[3px] ${s.border} ${s.card} transition-all duration-[180ms] hover:-translate-y-px hover:shadow-[0_6px_20px_rgba(0,0,0,.4),0_0_0_1px_#3A3D47] hover:z-10 group ${done ? 'opacity-30' : ''}`}>
      <div className="flex items-start justify-between gap-1">
        <span className={`text-[13px] font-semibold text-white truncate ${done ? 'line-through text-text-secondary' : ''}`}>{event.title || 'Untitled'}</span>
        {event.category !== 'break' && (
          <button onClick={e => { e.stopPropagation(); onComplete?.(event.id); }} className={`w-4 h-4 rounded border-[1.5px] flex items-center justify-center text-[10px] shrink-0 cursor-pointer transition-all duration-[180ms] ${done ? 'border-green text-green bg-green/10' : 'border-border-hover hover:border-cyan opacity-40 group-hover:opacity-100'}`}>
            {done ? '✓' : ''}
          </button>
        )}
      </div>
      <p className="font-mono text-[10px] text-text-tertiary/70 mt-0.5">{fmt(event.start)}–{fmt(event.end)} · {dur(event.duration_minutes)} · {event.priority || 'Medium'}</p>
      {event.status === 'in_progress' && (
        <div className="absolute bottom-0 inset-x-0 h-[3px] bg-white/[.025] rounded-b-[9px] overflow-hidden"><div className="h-full w-1/2 bg-gradient-to-r from-cyan to-cyan/50" /></div>
      )}
    </div>
  );
}
