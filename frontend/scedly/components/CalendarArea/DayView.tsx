'use client';
import EventBlock, { CalendarEvent } from './EventBlock';
import NowIndicator from './NowIndicator';

interface Props { date: Date; events: CalendarEvent[]; onComplete?: (id: string) => void; }

const START = 8, END = 22, H = 66;

function pos(event: CalendarEvent): React.CSSProperties {
  const s = new Date(event.start);
  const top = (s.getHours() + s.getMinutes() / 60 - START) * H;
  const height = Math.max((event.duration_minutes / 60) * H, 28);
  return { top, height };
}

export default function DayView({ date, events, onComplete }: Props) {
  const hours = Array.from({ length: END - START }, (_, i) => START + i);
  const day = date.toISOString().slice(0, 10);
  const dayEvents = events.filter(e => e.start?.startsWith(day));

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="flex relative" style={{ height: hours.length * H }}>
        {/* Gutter */}
        <div className="w-[52px] shrink-0 relative">
          {hours.map(h => (
            <div key={h} className="absolute right-0 pr-2.5" style={{ top: (h - START) * H, height: H }}>
              <span className="font-mono text-[10.5px] text-text-tertiary/60">{String(h).padStart(2, '0')}:00</span>
            </div>
          ))}
        </div>
        {/* Canvas */}
        <div className="flex-1 border-l border-border relative">
          {hours.map(h => (
            <div key={h} className="absolute left-0 right-0 h-px bg-border opacity-35" style={{ top: (h - START) * H }} />
          ))}
          <NowIndicator startHour={START} hourHeight={H} />
          {dayEvents.map(e => <EventBlock key={e.id} event={e} style={pos(e)} onComplete={onComplete} />)}
          {dayEvents.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="font-mono text-[11px] text-text-tertiary/50">no tasks scheduled — use chat to add some</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
