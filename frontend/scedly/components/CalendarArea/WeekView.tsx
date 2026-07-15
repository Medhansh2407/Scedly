'use client';
import EventBlock, { CalendarEvent } from './EventBlock';
import NowIndicator from './NowIndicator';

interface Props { date: Date; events: CalendarEvent[]; onComplete?: (id: string) => void; }

const START = 8, END = 22, H = 66, DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

function weekDates(d: Date): Date[] {
  const s = new Date(d); s.setDate(d.getDate() - d.getDay());
  return Array.from({ length: 7 }, (_, i) => { const x = new Date(s); x.setDate(s.getDate() + i); return x; });
}

export default function WeekView({ date, events, onComplete }: Props) {
  const week = weekDates(date);
  const hours = Array.from({ length: END - START }, (_, i) => START + i);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex border-b border-border shrink-0">
        <div className="w-[52px] shrink-0" />
        {week.map(d => {
          const isToday = d.toISOString().slice(0, 10) === today;
          return (
            <div key={d.toISOString()} className="flex-1 text-center py-2 border-l border-border/40">
              <div className="text-[10px] text-text-tertiary uppercase">{DAYS[d.getDay()]}</div>
              <div className={`text-[13px] font-medium mt-0.5 ${isToday ? 'w-7 h-7 rounded-full bg-cyan text-black mx-auto flex items-center justify-center' : ''}`}>{d.getDate()}</div>
            </div>
          );
        })}
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="flex relative" style={{ height: hours.length * H }}>
          <div className="w-[52px] shrink-0 relative">
            {hours.map(h => <div key={h} className="absolute right-0 pr-2.5" style={{ top: (h - START) * H }}><span className="font-mono text-[10.5px] text-text-tertiary/60">{String(h).padStart(2,'0')}:00</span></div>)}
          </div>
          {week.map(d => {
            const ds = d.toISOString().slice(0, 10);
            const isToday = ds === today;
            const de = events.filter(e => e.start?.startsWith(ds));
            return (
              <div key={ds} className={`flex-1 relative border-l border-border/40 ${isToday ? 'bg-cyan/[.02]' : ''}`}>
                {hours.map(h => <div key={h} className="absolute left-0 right-0 h-px bg-border opacity-35" style={{ top: (h - START) * H }} />)}
                {isToday && <NowIndicator startHour={START} hourHeight={H} />}
                {de.map(e => {
                  const s = new Date(e.start);
                  const top = (s.getHours() + s.getMinutes() / 60 - START) * H;
                  const height = Math.max((e.duration_minutes / 60) * H, 28);
                  return <EventBlock key={e.id} event={e} style={{ top, height }} onComplete={onComplete} />;
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
