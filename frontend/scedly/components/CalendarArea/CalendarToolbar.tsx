'use client';

export type CalendarView = 'day' | 'week' | 'month';

interface Props {
  currentDate: Date;
  view: CalendarView;
  onViewChange: (v: CalendarView) => void;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}

function formatLabel(date: Date, view: CalendarView): string {
  if (view === 'day') return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  if (view === 'week') {
    const s = new Date(date); s.setDate(date.getDate() - date.getDay());
    const e = new Date(s); e.setDate(s.getDate() + 6);
    return `${s.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${e.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
  }
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

export default function CalendarToolbar({ currentDate, view, onViewChange, onPrev, onNext, onToday }: Props) {
  const views: CalendarView[] = ['day', 'week', 'month'];
  return (
    <div className="bg-surface border-b border-border px-5 py-2.5 flex justify-between items-center shrink-0">
      <div className="flex items-center gap-1.5">
        <button onClick={onPrev} className="w-[30px] h-[30px] rounded-[7px] border border-border text-text-tertiary hover:text-white hover:border-border-hover hover:bg-white/[.03] flex items-center justify-center transition-all duration-150">‹</button>
        <button onClick={onNext} className="w-[30px] h-[30px] rounded-[7px] border border-border text-text-tertiary hover:text-white hover:border-border-hover hover:bg-white/[.03] flex items-center justify-center transition-all duration-150">›</button>
        <button onClick={onToday} className="px-3 py-1.5 rounded-[7px] border border-border text-[12px] font-medium text-text-tertiary hover:text-white hover:bg-cyan/[.06] hover:border-cyan/25 ml-1 transition-all duration-150">Today</button>
        <span className="text-[15px] font-semibold tracking-tight ml-3">{formatLabel(currentDate, view)}</span>
      </div>
      <div className="bg-bg rounded-[9px] p-[3px] flex">
        {views.map(v => (
          <button key={v} onClick={() => onViewChange(v)} className={`px-3.5 py-1.5 rounded-md text-[12px] capitalize transition-all duration-150 ${v === view ? 'bg-cyan text-black font-semibold shadow-[0_2px_8px_rgba(79,195,247,.2)]' : 'text-text-tertiary hover:text-text-secondary'}`}>{v}</button>
        ))}
      </div>
    </div>
  );
}
