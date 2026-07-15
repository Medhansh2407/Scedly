'use client';

export default function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[88%] bg-white/[.04] border border-border rounded-[14px_14px_4px_14px] px-3.5 py-2">
        <p className="font-mono text-[12px] text-text-secondary leading-relaxed whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
