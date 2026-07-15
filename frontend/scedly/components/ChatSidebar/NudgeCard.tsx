'use client';

interface Props {
  body: string;
  actions?: { label: string; variant: 'primary' | 'secondary' | 'dismiss' }[];
  onAction?: (label: string) => void;
}

export default function NudgeCard({ body, actions, onAction }: Props) {
  return (
    <div className="bg-amber/[.03] border border-amber/30 rounded-[11px] p-[13px] shadow-[0_0_20px_rgba(255,202,40,.04)]">
      <div className="text-[10px] uppercase tracking-wide font-semibold text-amber mb-2">💡 Behavioral nudge</div>
      <p className="text-[13px] text-text-secondary leading-relaxed mb-3 whitespace-pre-wrap">{body}</p>
      {actions && actions.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {actions.map(a => (
            <button key={a.label} onClick={() => onAction?.(a.label)} className={`px-3 py-1.5 rounded-[7px] text-[11px] font-semibold transition-all duration-150 ${a.variant === 'primary' ? 'bg-amber text-black border border-amber hover:opacity-85' : a.variant === 'dismiss' ? 'text-text-tertiary border border-transparent hover:text-text-secondary' : 'border border-border text-white'}`}>
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
