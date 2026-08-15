'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { useState } from 'react';

const fade = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0, transition: { duration: .45 } } };
const stagger = { show: { transition: { staggerChildren: .07 } } };
const nav = [['Product', 'product'], ['How it works', 'how'], ['Intelligence', 'intelligence'], ['Calendar', 'calendar'], ['Access', 'access']];

const workflow = [
  ['01', 'Describe the outcome', 'Write naturally. Scedly extracts the title, duration, earliest start, deadline, priority, energy level, and flexibility—asking only when an important detail is missing.'],
  ['02', 'Review the interpretation', 'Before committing anything, the agent explains what it understood. Correct a detail in the conversation and the plan changes with it.'],
  ['03', 'Get a viable schedule', 'The engine searches your working window, honors deadlines and protected time, avoids overlaps, and leaves impossible work unscheduled instead of pretending it fits.'],
  ['04', 'Adapt without rebuilding', 'Report a missed block, edit a task, or finish only part of it. Scedly repairs the affected work, preserves rigid events, and explains every move.'],
];

const rules = [
  ['Deadline-safe', 'Tasks must finish—not merely start—before their deadline.'],
  ['Energy-aware', 'Demanding work prefers your peak window; lighter work uses lower-energy time.'],
  ['Recovery-aware', 'High-energy blocks receive breathing room instead of being packed together.'],
  ['Conflict-free', 'Existing blocks stay protected, with approval requested for disruptive choices.'],
  ['Start-aware', '“After Wednesday” and other earliest-start constraints are respected.'],
  ['Focus-protecting', 'Working hours, focus hours, timezone, and rigid tasks shape every decision.'],
];

const intelligence = [
  ['↻', 'Missed-time recovery', 'Say “I missed this morning.” Scedly finds affected tasks, orders them by deadline and priority, and moves only the work that needs repair.'],
  ['½', 'Partial-task continuation', 'If a block was partly completed, progress is preserved and the remaining duration becomes a linked continuation task.'],
  ['≋', 'Long-task splitting', 'Large work can be divided across multiple viable blocks instead of requiring one unrealistic opening.'],
  ['◎', 'Personal preferences', 'Working windows, focus hours, energy windows, and timezone are available in onboarding, settings, and conversation.'],
  ['∞', 'Context and memory', 'Chat history, session summaries, relevant memories, and past-task patterns help the agent carry decisions forward.'],
  ['?', 'Transparent escalation', 'When the ideal slot does not exist, Scedly proposes flexible moves or out-of-window options—and waits for approval.'],
];

const surfaces = [
  ['WEB', 'Chat, calendar, task list, onboarding, and settings in one dashboard.'],
  ['CLI', 'Stream chat replies, list tasks, and inspect the schedule from your terminal.'],
  ['TELEGRAM', 'Link your account and send scheduling requests from a phone-friendly chat.'],
  ['MCP', 'Give compatible AI clients tools for tasks, schedules, completion, rescheduling, and preferences.'],
  ['GOOGLE CALENDAR', 'Connect and synchronize events with the same scheduling system.'],
  ['OUTLOOK', 'Connect Microsoft Calendar and keep events aligned with the plan.'],
];

function useTheme() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => typeof window === 'undefined' ? 'dark' : (localStorage.getItem('scedly-theme') as 'dark' | 'light' | null) || 'dark');
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next); localStorage.setItem('scedly-theme', next);
    document.documentElement.classList.toggle('light', next === 'light');
    document.documentElement.classList.toggle('dark', next === 'dark');
  };
  return { theme, toggle };
}

function Nav({ theme, toggle }: { theme: 'dark' | 'light'; toggle: () => void }) {
  return <nav className="sticky top-0 z-50 border-b border-border bg-[var(--bg)]/85 backdrop-blur-xl">
    <div className="mx-auto flex h-16 max-w-content items-center justify-between px-5 md:px-6">
      <Link href="/" aria-label="Scedly home" className="flex items-center gap-2.5"><span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-[var(--logo-from)] to-[var(--logo-to)] shadow-[var(--logo-shadow)]">{theme === 'dark' ? '◐' : '◑'}</span><span className="font-mono font-bold text-text-primary">scedly<span className="animate-blink text-term-green">_</span></span></Link>
      <div className="hidden items-center gap-7 lg:flex">{nav.map(([label, id]) => <a key={id} href={`#${id}`} className="text-sm font-medium text-text-secondary transition-colors hover:text-text-primary">{label}</a>)}</div>
      <div className="flex items-center gap-2.5"><button type="button" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface">{theme === 'dark' ? '☾' : '☀'}</button><Link href="/login" className="hidden rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-semibold sm:inline-flex">Sign in</Link><Link href="/login" className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#04121f] shadow-[0_6px_18px_-6px_var(--accent)]">Open Scedly</Link></div>
    </div>
  </nav>;
}

function Terminal({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="overflow-hidden rounded-card border border-border-strong bg-term-bg font-mono shadow-card"><div className="flex items-center gap-2 border-b border-border-strong bg-[#0d1118] px-3.5 py-2.5"><span className="h-3 w-3 rounded-sm bg-pri-high"/><span className="h-3 w-3 rounded-sm bg-pri-med"/><span className="h-3 w-3 rounded-sm bg-pri-low"/><span className="ml-2 text-xs text-term-dim">{title}</span></div><div className="p-4 text-sm leading-[1.85] text-[#c6d4cb]">{children}</div></div>;
}

function Heading({ eyebrow, title, copy }: { eyebrow: string; title: string; copy?: string }) {
  return <div className="mx-auto max-w-3xl text-center"><span className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[.18em] text-accent before:inline-block before:h-0.5 before:w-4 before:bg-accent before:content-['']">{eyebrow}</span><h2 className="mt-4 text-[clamp(1.8rem,3.2vw,2.65rem)] font-[680] leading-[1.1] tracking-tight text-text-primary">{title}</h2>{copy && <p className="mx-auto mt-4 max-w-[62ch] text-lg text-text-secondary">{copy}</p>}</div>;
}

function Hero() {
  return <header className="overflow-hidden py-16 md:py-24"><div className="mx-auto grid max-w-content items-center gap-14 px-5 md:grid-cols-[1.04fr_.96fr] md:px-6">
    <motion.div initial="hidden" animate="show" variants={stagger}><motion.span variants={fade} className="mb-5 inline-flex items-center gap-2 rounded-full border border-[rgba(76,195,138,.4)] px-3 py-1 font-mono text-xs font-semibold text-pri-low"><span className="h-2 w-2 rounded-full bg-pri-low shadow-[0_0_7px_#4cc38a]"/>An agent that turns intent into protected time</motion.span><motion.h1 variants={fade} className="text-[clamp(2.55rem,5.5vw,4.35rem)] font-[700] leading-[1.02] tracking-[-.045em] text-text-primary">Tell Scedly what matters.<br/>It builds the plan.</motion.h1><motion.p variants={fade} className="mt-5 max-w-[60ch] text-lg leading-relaxed text-text-secondary">Scedly is a conversational scheduling agent. Describe work in plain English and it turns tasks, deadlines, energy needs, and availability into a conflict-free calendar—then repairs the plan when the day changes.</motion.p><motion.div variants={fade} className="mt-8 flex flex-wrap gap-3"><Link href="/login" className="rounded-lg bg-accent px-6 py-3 font-semibold text-[#04121f] shadow-[0_6px_18px_-6px_#5bb8ff]">Open Scedly →</Link><a href="#product" className="rounded-lg border border-border-strong px-6 py-3 font-semibold text-text-primary hover:bg-surface-2">Explore the product</a></motion.div><motion.div variants={fade} className="mt-6 flex flex-wrap gap-x-5 gap-y-2 font-mono text-xs text-text-tertiary"><span>Natural-language planning</span><span>Adaptive rescheduling</span><span>Calendar sync</span></motion.div></motion.div>
    <motion.div initial={{opacity:0,x:28}} animate={{opacity:1,x:0}} transition={{delay:.25,duration:.6}}><Terminal title="scedly — plan today"><div><b className="text-accent">[you]:</b> finish the launch brief, 90m, after 11, due tomorrow</div><div className="mt-2"><b className="text-term-green">scedly&gt;</b> <span className="text-pri-low">✓ Launch brief · today 11:30–13:00</span></div><div className="text-term-dim">  high energy · deadline protected · no conflicts</div><div className="mt-3"><b className="text-accent">[you]:</b> the meeting ran long—i finished half</div><div className="mt-2"><b className="text-term-green">scedly&gt;</b> <span className="text-pri-med">↻ Saved progress and created a 45m continuation</span></div><div className="text-term-dim">  continuation → 15:00 · admin review → 16:00</div><div className="mt-3"><b className="text-accent">[you]:</b> why 3pm?</div><div className="mt-2"><b className="text-term-green">scedly&gt;</b> First open block before the deadline that preserves rigid events.<span className="ml-1 inline-block h-[1.05em] w-2 animate-blink bg-term-green align-[-2px]"/></div></Terminal></motion.div>
  </div></header>;
}

function Product() {
  return <section id="product" className="border-y border-border bg-bg-elev py-24"><div className="mx-auto max-w-content px-5 md:px-6"><Heading eyebrow="The product" title="From a sentence to a schedule you can trust." copy="Scedly combines a conversational task manager with a constraint-aware calendar. The chat is the control surface; the schedule is the result."/><motion.div initial="hidden" whileInView="show" viewport={{once:true}} variants={stagger} className="mt-12 grid gap-5 md:grid-cols-2">{workflow.map(([num,title,copy]) => <motion.article key={num} variants={fade} className="rounded-card border border-border bg-surface p-6 transition-all hover:-translate-y-1 hover:border-border-strong hover:shadow-card"><span className="font-mono text-xs text-accent">{num} / workflow</span><h3 className="mt-3 text-xl font-semibold text-text-primary">{title}</h3><p className="mt-2 leading-relaxed text-text-secondary">{copy}</p></motion.article>)}</motion.div></div></section>;
}

function How() {
  return <section id="how" className="py-24"><div className="mx-auto grid max-w-content gap-12 px-5 md:grid-cols-[.9fr_1.1fr] md:px-6"><div><Heading eyebrow="How scheduling works" title="Rules first. Intelligence on top." copy="A dedicated scheduling engine checks the constraints that make a plan workable."/><div className="mt-8"><Terminal title="scedly — constraint check"><div className="text-term-dim">$ schedule &quot;prepare demo&quot; --duration 120m</div>{['starts after requested date','ends before deadline','inside working window','peak-energy preference matched','recovery gap preserved','0 calendar conflicts'].map(x=><div key={x}><span className="text-pri-low">✓</span> {x}</div>)}<div className="mt-2 text-accent">→ Tue 09:30–11:30</div></Terminal></div></div><motion.div initial="hidden" whileInView="show" viewport={{once:true}} variants={stagger} className="grid content-start gap-4 sm:grid-cols-2">{rules.map(([title,copy],i)=><motion.article key={title} variants={fade} className="rounded-card border border-border bg-surface p-5"><div className="grid h-7 w-7 place-items-center rounded-md bg-surface-2 font-mono text-xs text-accent">{String(i+1).padStart(2,'0')}</div><h3 className="mt-4 font-semibold text-text-primary">{title}</h3><p className="mt-2 text-sm leading-relaxed text-text-secondary">{copy}</p></motion.article>)}</motion.div></div></section>;
}

function Intelligence() {
  return <section id="intelligence" className="border-y border-border bg-bg-elev py-24"><div className="mx-auto max-w-content px-5 md:px-6"><Heading eyebrow="Adaptive intelligence" title="A plan that survives contact with real life." copy="Scedly keeps task state, conversation context, and the reasoning needed to recover when reality diverges from the plan."/><motion.div initial="hidden" whileInView="show" viewport={{once:true}} variants={stagger} className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">{intelligence.map(([icon,title,copy])=><motion.article key={title} variants={fade} className="rounded-card border border-border bg-surface p-5 transition-all hover:-translate-y-1 hover:border-border-strong hover:shadow-card"><div className="grid h-7 w-7 place-items-center rounded-md bg-accent text-xs font-bold text-[#04121f]">{icon}</div><h3 className="mt-4 text-lg font-semibold text-text-primary">{title}</h3><p className="mt-2 text-sm leading-relaxed text-text-secondary">{copy}</p></motion.article>)}</motion.div></div></section>;
}

function Calendar() {
  const events: Record<string,[string,string]> = {'0-0':['Launch brief','border-accent bg-accent/10 text-accent'],'1-2':['Design review','border-pri-med bg-pri-med/10 text-pri-med'],'3-1':['Inbox + admin','border-pri-low bg-pri-low/10 text-pri-low']};
  return <section id="calendar" className="py-24"><div className="mx-auto grid max-w-content items-center gap-12 px-5 md:grid-cols-[1.08fr_.92fr] md:px-6"><div className="overflow-hidden rounded-card border border-border bg-surface shadow-card"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><div className="font-mono text-xs text-text-tertiary">CALENDAR / WEEK</div><b className="mt-1 block text-text-primary">Your plan, at a glance</b></div><div className="flex gap-1 rounded-lg bg-surface-2 p-1 font-mono text-[10px]"><span className="px-2 py-1">DAY</span><span className="rounded bg-accent px-2 py-1 text-[#04121f]">WEEK</span><span className="px-2 py-1">MONTH</span></div></div><div className="grid grid-cols-[60px_repeat(3,1fr)] text-xs"><div className="border-b border-r border-border p-2 text-text-tertiary">TIME</div>{['TUE 12','WED 13','THU 14'].map(x=><div key={x} className="border-b border-r border-border p-2 text-center font-mono text-text-secondary">{x}</div>)}{['09:00','11:00','13:00','15:00'].map((time,row)=><div key={time} className="contents"><div className="min-h-20 border-b border-r border-border p-2 font-mono text-[10px] text-text-tertiary">{time}</div>{[0,1,2].map(col=>{const e=events[`${row}-${col}`];return <div key={col} className="min-h-20 border-b border-r border-border p-1.5">{e&&<div className={`h-full rounded-md border-l-2 p-2 font-medium ${e[1]}`}>{e[0]}<div className="mt-1 font-mono text-[9px] opacity-70">scheduled</div></div>}</div>})}</div>)}</div></div><div><span className="font-mono text-xs uppercase tracking-[.18em] text-accent">Calendar and tasks</span><h2 className="mt-4 text-[clamp(1.8rem,3.2vw,2.65rem)] font-[680] leading-[1.1] tracking-tight text-text-primary">See the plan. Track the work.</h2><p className="mt-4 text-lg leading-relaxed text-text-secondary">Day, week, and month views show scheduled work as priority-coded blocks. The task list keeps scheduled and unscheduled items visible, while explicit completion controls what enters your weekly record.</p><div className="mt-7 space-y-3">{[['PENDING','Unscheduled or waiting to begin','text-pri-med'],['IN PROGRESS','Currently inside its scheduled block','text-accent'],['DONE THIS WEEK','Completed work kept in weekly context','text-pri-low']].map(([s,d,c])=><div key={s} className="flex gap-4 rounded-lg border border-border bg-surface p-4"><span className={`min-w-28 font-mono text-xs ${c}`}>{s}</span><span className="text-sm text-text-secondary">{d}</span></div>)}</div></div></div></section>;
}

function Access() {
  return <section id="access" className="border-y border-border bg-bg-elev py-24"><div className="mx-auto max-w-content px-5 md:px-6"><Heading eyebrow="One system, multiple surfaces" title="Use Scedly where the work begins." copy="Every interface talks to the same authenticated task, preference, and scheduling backend."/><motion.div initial="hidden" whileInView="show" viewport={{once:true}} variants={stagger} className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-3">{surfaces.map(([name,copy])=><motion.article key={name} variants={fade} className="rounded-card border border-border bg-surface p-5"><span className="font-mono text-xs text-accent">{name}</span><p className="mt-3 text-sm leading-relaxed text-text-secondary">{copy}</p></motion.article>)}</motion.div><div className="mt-12 grid gap-5 md:grid-cols-2"><Terminal title="terminal — scedly"><div className="text-term-dim">$ scedly chat &quot;block 45m for release notes tomorrow&quot;</div><div className="mt-2"><span className="text-pri-low">✓ Release notes</span> · Wed 10:15–11:00</div><div className="mt-3 text-term-dim">$ scedly schedule</div><div>10:15–11:00 <span className="text-accent">Release notes</span></div><div>14:00–14:30 Product sync</div></Terminal><Terminal title="mcp — scedly tools">{['create_task','list_tasks','get_schedule','reschedule','mark_complete','update_preferences'].map(x=><div key={x}><span className="text-accent-2">{x}</span> <span className="text-term-dim">→ connected scheduling tool</span></div>)}</Terminal></div></div></section>;
}

function Foundation() {
  const items=['Google or GitHub OAuth','User-isolated tasks and history','API keys for non-web clients','Token-streamed chat replies','Persistent preferences and timezone','Task search and calendar APIs'];
  return <section className="py-24"><div className="mx-auto max-w-content px-5 md:px-6"><div className="rounded-card border border-border-strong bg-surface p-7 shadow-card md:p-10"><div className="grid gap-10 md:grid-cols-[.8fr_1.2fr] md:items-center"><div><span className="font-mono text-xs uppercase tracking-[.18em] text-accent">The foundation</span><h2 className="mt-4 text-3xl font-[680] tracking-tight text-text-primary">A complete product loop, not a calendar mockup.</h2><p className="mt-4 leading-relaxed text-text-secondary">Authentication, persistence, streaming, preferences, search, and programmatic access support the scheduling experience end to end.</p></div><div className="grid gap-3 sm:grid-cols-2">{items.map(x=><div key={x} className="flex items-center gap-3 rounded-lg border border-border bg-bg-elev px-4 py-3 text-sm text-text-secondary"><span className="text-pri-low">✓</span>{x}</div>)}</div></div></div></div></section>;
}

function Footer() {
  return <><section className="border-t border-border bg-bg-elev py-24 text-center"><div className="mx-auto max-w-content px-5"><span className="font-mono text-xs uppercase tracking-[.18em] text-accent">Your time, expressed as intent</span><h2 className="mt-4 text-[clamp(2rem,4vw,3.25rem)] font-[700] leading-tight tracking-tight text-text-primary">Stop arranging blocks.<br/>Start describing what needs to happen.</h2><p className="mx-auto mt-4 max-w-[56ch] text-lg text-text-secondary">Scedly translates the rest into a schedule—and stays with the plan when the day moves.</p><Link href="/login" className="mt-7 inline-flex rounded-lg bg-accent px-6 py-3 font-semibold text-[#04121f]">Open Scedly →</Link></div></section><footer className="border-t border-border py-10"><div className="mx-auto flex max-w-content flex-col gap-6 px-5 md:px-6"><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center"><Link href="/" className="font-mono font-bold text-text-primary">scedly<span className="animate-blink text-term-green">_</span></Link><div className="flex flex-wrap gap-5 text-sm text-text-secondary">{nav.map(([l,id])=><a key={id} href={`#${id}`}>{l}</a>)}<Link href="/login">Sign in</Link></div></div><div className="h-px bg-border"/><div className="flex flex-col justify-between gap-3 font-mono text-xs text-text-tertiary sm:flex-row"><span>© Scedly. All rights reserved.</span><span>Natural-language scheduling that adapts.</span></div></div></footer></>;
}

export default function LandingPage() {
  const { theme, toggle } = useTheme();
  const vars = {'--bg':theme==='dark'?'#0a0c10':'#faf8f3','--bg-elev':theme==='dark'?'#0e1118':'#fff','--surface':theme==='dark'?'#12161f':'#fff','--surface-2':theme==='dark'?'#161b26':'#f6f3ec','--surface-3':theme==='dark'?'#1b212e':'#efeadf','--border':theme==='dark'?'#232a37':'#e7e1d4','--border-strong':theme==='dark'?'#303a4b':'#d8d0bd','--text':theme==='dark'?'#e7edf4':'#1b1f27','--text-muted':theme==='dark'?'#8b97a8':'#5d6470','--text-faint':theme==='dark'?'#5c6675':'#939aa6','--term-green':theme==='dark'?'#6ee7a0':'#1f8a52','--term-dim':theme==='dark'?'#587462':'#749281','--term-bg':theme==='dark'?'#07090d':'#1d2230','--accent':theme==='dark'?'#5bb8ff':'#2f7fe0','--accent-2':theme==='dark'?'#8b7dff':'#6a5cf0','--pri-high':'#ef5350','--pri-med':theme==='dark'?'#ffc93c':'#d99500','--pri-low':theme==='dark'?'#4cc38a':'#1f9d63','--logo-from':theme==='dark'?'#2b3550':'#ffc93c','--logo-to':theme==='dark'?'#1a2236':'#ff9d3c','--logo-shadow':'0 0 0 1px rgba(255,255,255,.06) inset,0 4px 16px -6px #5bb8ff'} as React.CSSProperties;
  return <div style={vars}><div className="min-h-screen bg-[var(--bg)] text-[var(--text)] transition-colors" style={{backgroundImage:theme==='dark'?'radial-gradient(rgba(255,255,255,.022) 1px,transparent 1px)':'radial-gradient(rgba(0,0,0,.03) 1px,transparent 1px)',backgroundSize:'28px 28px',backgroundAttachment:'fixed'}}><Nav theme={theme} toggle={toggle}/><main><Hero/><Product/><How/><Intelligence/><Calendar/><Access/><Foundation/></main><Footer/></div></div>;
}
