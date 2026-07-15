'use client';
import { CalendarEvent } from './EventBlock';

interface Props { date: Date; events: CalendarEvent[]; }

const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const pri: Record<string, string> = { High: 'border-l-red', Medium: 'border-l-amber', Low: 'border-l-green' };

function grid(date: Date): (Date | null)[][] {
  const y = date.getFullYear(), m = date.getMonth();
  const first = new Date(y, m, 1).getDay(), days = new Date(y, m + 1, 0).getDate();
  const weeks: (Date | null)[][] = [];
  let w: (Date | null)[] = Array(first).fill(null);
  for (let d = 1; d <= days; d++) { w.push(new Date(y, m, d)); if (w.length === 7) { weeks.push(w); w = []; } }
  if (w.length) { while (w.length < 7) w.push(null); weeks.push(w); }
  return weeks;
}

export default function MonthView({ date, events }: Props) {
  const weeks = grid(date);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin p-3">
      <div className="grid grid-cols-7 gap-px mb-1">
        {DAYS.map(d => <div key={d} className="text-[10px] text-text-tertiary text-center uppercase py-1">{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-px flex-1">
        {weeks.flat().map((day, i) => {
          if (!day) return <div key={i} className="min-h-[100px] bg-bg rounded-[7px]" />;
          const ds = day.toISOString().slice(0, 10);
          const isToday = ds === today;
          const de = events.filter(e => e.start?.startsWith(ds));
          return (
            <div key={i} className={`min-h-[100px] p-2 rounded-[7px] hover:bg-surface transition-colors ${isToday ? 'bg-cyan/[.03]' : 'bg-bg'}`}>
              <div className={`text-[12px] mb-1 ${isToday ? 'text-cyan font-semibold' : 'text-text-secondary'}`}>{day.getDate()}</div>
              <div className="space-y-0.5">
                {de.slice(0, 3).map(e => <div key={e.id} className={`text-[10px] truncate px-1 py-0.5 rounded-sm border-l-2 ${pri[e.priority || 'Medium']} bg-surface/50 text-text-secondary`}>{e.title}</div>)}
                {de.length > 3 && <div className="text-[10px] text-text-tertiary pl-1">+{de.length - 3} more</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
