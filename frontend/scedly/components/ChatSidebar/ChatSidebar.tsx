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
      <button
        onClick={onToggle}
        aria-label="Open chat"
        className="flex h-12 w-full shrink-0 items-center justify-center border-t border-border bg-surface transition-all duration-200 hover:bg-white/[.02] md:h-auto md:w-12 md:flex-col md:border-l md:border-t-0"
      >
        <span className="text-lg">💬</span>
      </button>
    );
  }

  return (
    <div className="flex h-[44%] w-full shrink-0 flex-col border-t border-border bg-surface transition-all duration-200 md:h-auto md:w-[360px] md:border-l md:border-t-0">
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
