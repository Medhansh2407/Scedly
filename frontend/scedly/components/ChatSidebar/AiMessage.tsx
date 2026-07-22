'use client';

interface Props { content: string; streaming?: boolean; }

export default function AiMessage({ content, streaming }: Props) {
  const isError = content.startsWith('Backend error') || content.startsWith('Could not reach') || content.startsWith('AI error') || content.startsWith('Stream interrupted');

  return (
    <div className="flex flex-col gap-1">
      <span className={`font-mono text-[11px] font-medium ${isError ? 'text-red' : 'text-cyan'}`}>scedly&gt;</span>
      <p className={`font-sans text-[13px] leading-relaxed whitespace-pre-wrap ${isError ? 'text-red/80' : 'text-text-secondary'}`}>
        {content || (streaming ? '' : '…')}
        {streaming && <span className="inline-block w-[2px] h-3.5 bg-cyan ml-0.5 animate-pulse align-middle" />}
      </p>
      {isError && <p className="font-mono text-[10px] text-text-tertiary mt-0.5">↳ please try again in a moment</p>}
    </div>
  );
}
