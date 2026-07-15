'use client';
import MessageList, { ChatMsg } from './MessageList';
import ChatInput from './ChatInput';

interface Props {
  messages: ChatMsg[];
  onSend: (msg: string) => void;
  sending?: boolean;
  open: boolean;
  onToggle: () => void;
  onNudgeAction?: (msgId: string, action: string) => void;
}

export default function ChatSidebar({ messages, onSend, sending, open, onToggle, onNudgeAction }: Props) {
  if (!open) {
    return (
      <button onClick={onToggle} className="w-12 border-l border-border bg-surface flex flex-col items-center justify-center shrink-0 hover:bg-white/[.02] transition-all duration-200">
        <span className="text-lg">💬</span>
      </button>
    );
  }

  return (
    <div className="w-[360px] border-l border-border bg-surface flex flex-col shrink-0 transition-all duration-200">
      <div className="h-[46px] flex items-center justify-between px-4 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span>💬</span>
          <span className="text-[13px] font-medium text-text-secondary">Chat with Scedly</span>
        </div>
        <button onClick={onToggle} className="text-[11px] text-text-tertiary hover:text-white transition-all duration-150 cursor-pointer">collapse ›</button>
      </div>
      <MessageList messages={messages} onNudgeAction={onNudgeAction} />
      <ChatInput onSend={onSend} disabled={sending} />
    </div>
  );
}
