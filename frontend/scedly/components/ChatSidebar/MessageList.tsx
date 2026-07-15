'use client';
import { useEffect, useRef } from 'react';
import UserMessage from './UserMessage';
import AiMessage from './AiMessage';
import NudgeCard from './NudgeCard';

export interface ChatMsg {
  id: string;
  role: 'user' | 'assistant' | 'nudge';
  content: string;
  streaming?: boolean;
  nudgeActions?: { label: string; variant: 'primary' | 'secondary' | 'dismiss' }[];
}

interface Props { messages: ChatMsg[]; onNudgeAction?: (msgId: string, action: string) => void; }

export default function MessageList({ messages, onNudgeAction }: Props) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin p-4 flex flex-col gap-4">
      {messages.map(m => {
        if (m.role === 'user') return <UserMessage key={m.id} content={m.content} />;
        if (m.role === 'nudge') return <NudgeCard key={m.id} body={m.content} actions={m.nudgeActions} onAction={a => onNudgeAction?.(m.id, a)} />;
        return <AiMessage key={m.id} content={m.content} streaming={m.streaming} />;
      })}
      <div ref={bottom} />
    </div>
  );
}
