'use client';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useState } from 'react';

const fadeUp = { hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: 0.5 } } };
const stagger = { show: { transition: { staggerChildren: 0.1 } } };

function useTheme() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window === 'undefined') return 'dark';
    return (localStorage.getItem('scedly-theme') as 'dark' | 'light' | null) || 'dark';
  });
  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('scedly-theme', next);
  }
  return { theme, toggle };
}

function Nav({ theme, toggle }: { theme: string; toggle: () => void }) {
  return (
    <nav className="sticky top-0 z-50 backdrop-blur-md bg-[var(--bg)]/80 border-b border-[var(--border)]">
      <div className="max-w-content mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-[var(--logo-from)] to-[var(--logo-to)] grid place-items-center text-sm shadow-[var(--logo-shadow)]">{theme === 'dark' ? '🌙' : '☀'}</span>
          <span className="font-mono font-bold text-[var(--text)]">scedly<span className="text-[var(--term-green)] animate-blink">_</span></span>
        </Link>
        <div className="hidden md:flex items-center gap-7">
          {['Why Scedly','How it works','Features','Channels','CLI','MCP','Pricing'].map(s => (
            <a key={s} href={`#${s.toLowerCase().replace(/\s+/g,'')}`} className="text-[var(--text-muted)] text-sm font-medium hover:text-[var(--text)] transition-colors">{s}</a>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={toggle} className="w-9 h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] grid place-items-center text-base hover:border-[var(--border-strong)] transition-all">{theme === 'dark' ? '🌙' : '☀'}</button>
          <Link href="/login" className="px-4 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)] text-sm font-semibold hover:bg-[var(--surface-3)] transition-colors">Sign in</Link>
          <Link href="/login" className="px-4 py-2 rounded-lg bg-[var(--accent)] text-[#04121f] text-sm font-semibold shadow-[0_6px_18px_-6px_var(--accent)] hover:brightness-110 transition-all">Get started free</Link>
        </div>
      </div>
    </nav>
  );
}

function TerminalWindow({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-term-bg border border-border-strong rounded-card overflow-hidden shadow-card font-mono">
      <div className="flex items-center gap-2 px-3.5 py-2.5 bg-[#0d1118] border-b border-border-strong">
        <div className="flex gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-pri-high" />
          <span className="w-3 h-3 rounded-sm bg-pri-med" />
          <span className="w-3 h-3 rounded-sm bg-pri-low" />
        </div>
        <span className="ml-2 text-xs text-term-dim tracking-wide">{title}</span>
      </div>
      <div className="p-4 text-sm leading-[1.85] text-[#c6d4cb]">{children}</div>
    </div>
  );
}

function Hero() {
  return (
    <header className="py-16 md:py-20">
      <div className="max-w-content mx-auto px-6 grid md:grid-cols-[1.05fr_1fr] gap-14 items-center">
        <motion.div initial="hidden" animate="show" variants={stagger}>
          <motion.span variants={fadeUp} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[rgba(76,195,138,0.4)] text-pri-low font-mono text-xs font-semibold mb-5">
            <span className="w-2 h-2 rounded-full bg-pri-low shadow-[0_0_6px_#4cc38a]" />For founders who ship
          </motion.span>
          <motion.h1 variants={fadeUp} className="text-[clamp(2.3rem,5vw,3.6rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">
            Why waste time<br />managing your own time?
          </motion.h1>
          <motion.p variants={fadeUp} className="mt-4 text-lg text-text-secondary max-w-[56ch]">
            Other calendars are dumb — they just store events. <span className="text-text-primary font-semibold">Scedly</span> schedules your day around your energy, reshuffles when you slip, and learns your patterns over weeks. Talk to it like a terminal; it does the rest.
          </motion.p>
          <motion.div variants={fadeUp} className="flex flex-wrap gap-3 mt-8">
            <Link href="/login" className="px-6 py-3 rounded-lg bg-accent text-[#04121f] font-semibold shadow-[0_6px_18px_-6px_#5bb8ff] hover:brightness-110 transition-all">Start free →</Link>
            <Link href="/app" className="px-6 py-3 rounded-lg border border-border-strong text-text-primary font-semibold hover:bg-surface-2 transition-colors">See the dashboard</Link>
          </motion.div>
          <motion.div variants={fadeUp} className="flex flex-wrap gap-4 mt-6 font-mono text-xs text-text-tertiary">
            <span>✓ No credit card</span><span>✓ 30 tasks/mo free</span><span>✓ Google & GitHub login</span>
          </motion.div>
        </motion.div>

        <motion.div initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3, duration: 0.6 }}>
          <TerminalWindow title="scedly — ~/today">
            <Line usr>draft the investor update, ~2h, due friday</Line>
            <Line bot ok>✓ Scheduled &quot;Investor update&quot; — Thu 09:00–11:00</Line>
            <Line comment>  ↳ High-focus work placed in your morning peak. Deadline Fri 17:00 — 1 day of buffer.</Line>
            <Line usr mt>i missed this morning</Line>
            <Line bot warn>↻ Rescheduled 2 tasks</Line>
            <Line comment>  ↳ &quot;Investor update&quot; → Thu 14:00–16:00 · &quot;Gym&quot; → 18:00 (evening, low-energy)</Line>
            <Line usr mt>why thursday afternoon?</Line>
            <Line comment>  <span className="text-term-green font-bold">scedly&gt;</span> Morning filled up after the slip. Afternoon is your next focus block before the deadline.</Line>
            <Line usr mt><span className="inline-block w-2 h-[1.05em] bg-term-green align-[-2px] animate-blink" /></Line>
          </TerminalWindow>
        </motion.div>
      </div>
    </header>
  );
}

function Line({ children, usr, bot, comment, ok, warn, info, mt }: { children: React.ReactNode; usr?: boolean; bot?: boolean; comment?: boolean; ok?: boolean; warn?: boolean; info?: boolean; mt?: boolean }) {
  const cls = [
    'whitespace-pre-wrap',
    mt && 'mt-3',
    comment && 'text-term-dim',
  ].filter(Boolean).join(' ');
  if (usr) return <div className={cls}><span className="text-[#5bb8ff] font-bold">[User]:</span> <span className="text-[#e7edf4]">{children}</span></div>;
  if (bot) return <div className={cls}><span className="text-term-green font-bold">scedly&gt;</span> <span className={ok ? 'text-pri-low' : warn ? 'text-pri-med' : info ? 'text-accent' : ''}>{children}</span></div>;
  return <div className={cls}>{children}</div>;
}

function ChannelStrip() {
  return (
    <div className="max-w-content mx-auto px-6">
      <div className="border-t border-dashed border-[var(--border-strong)]" />
      <div className="flex justify-center flex-wrap gap-9 py-5 font-mono text-xs text-[var(--text-faint)]">
        {['WEB','CLI','SLACK','TELEGRAM','GOOGLE CHAT','MCP','GMAIL'].map(c => <span key={c}>{c}</span>)}
      </div>
      <div className="border-t border-dashed border-[var(--border-strong)]" />
    </div>
  );
}

function Problem() {
  const cards = [
    { icon: '!', color: 'bg-pri-high', title: "It doesn't know your energy", desc: "Deep work gets dumped at 4pm next to three meetings. No recovery time, no peak-hour awareness." },
    { icon: '×', color: 'bg-accent', title: "It breaks the moment you slip", desc: "Miss one morning and the whole week is wrong. You spend Sunday night rebuilding it by hand." },
    { icon: '$', color: 'bg-coin', title: "It never gets smarter", desc: "You skip the gym every Thursday for a month and it keeps booking it Thursday. No memory, no coaching." },
  ];
  return (
    <section id="whyscedly" className="py-24">
      <div className="max-w-content mx-auto px-6 text-center">
        <span className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">The problem</span>
        <h2 className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">Every calendar app makes <em>you</em> do the work.</h2>
        <p className="mt-4 text-lg text-text-secondary max-w-[56ch] mx-auto">Dragging blocks, guessing durations, reshuffling by hand when a meeting runs over. Your calendar records time — it doesn&apos;t protect it.</p>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={stagger} className="grid md:grid-cols-3 gap-5 mt-12 text-left">
          {cards.map(c => (
            <motion.div key={c.title} variants={fadeUp} className="bg-surface border border-border rounded-card p-5 shadow-sm">
              <div className={`w-6 h-6 rounded ${c.color} grid place-items-center text-xs font-bold text-[#04121f] shadow-[inset_-3px_-3px_0_rgba(0,0,0,.22),inset_3px_3px_0_rgba(255,255,255,.28)]`}>{c.icon}</div>
              <h3 className="mt-4 text-lg font-semibold text-text-primary">{c.title}</h3>
              <p className="mt-2 text-sm text-text-secondary">{c.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    { num: '01', title: 'Say it in plain English', desc: '"Study for the exam 2 hours, sometime before Thursday." No forms, no dropdowns.', term: <><span className="text-[#5bb8ff]">[User]:</span> <span className="text-[#e7edf4]">study 2h before thu</span></> },
    { num: '02', title: 'It places it intelligently', desc: 'Priority, energy level, deadline and your working window decide the slot — conflict-free.', term: <><span className="text-pri-low">✓ Wed 09:00–11:00</span><br /><span className="text-term-dim">  high-focus · morning peak</span></> },
    { num: '03', title: 'It reshuffles when life happens', desc: "Miss a block? It reschedules only what's affected and tells you exactly what moved and why.", term: <><span className="text-pri-med">↻ moved to 14:00</span><br /><span className="text-term-dim">  morning is now full</span></> },
  ];
  return (
    <section id="howitworks" className="py-24 bg-bg-elev border-y border-border">
      <div className="max-w-content mx-auto px-6">
        <div className="text-center">
          <span className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">How it works</span>
          <h2 className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">Talk. It schedules. It adapts.</h2>
        </div>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={stagger} className="grid md:grid-cols-3 gap-5 mt-12">
          {steps.map(s => (
            <motion.div key={s.num} variants={fadeUp} className="bg-surface border border-border rounded-card p-5 hover:-translate-y-1 hover:border-border-strong hover:shadow-card transition-all">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-border bg-surface-2 font-mono text-xs text-text-secondary">{s.num}</span>
              <h3 className="mt-4 text-lg font-semibold text-text-primary">{s.title}</h3>
              <p className="mt-2 text-sm text-text-secondary">{s.desc}</p>
              <div className="mt-4 bg-term-bg border border-border-strong rounded-lg overflow-hidden">
                <div className="px-3.5 py-2.5 font-mono text-xs leading-relaxed text-[#c6d4cb]">{s.term}</div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function Features() {
  const items = [
    { icon: '⚡', color: 'bg-pri-high', title: 'Energy-aware placement', desc: 'High-focus work lands in your peak hours with 30-min recovery buffers between demanding tasks.' },
    { icon: '↻', color: 'bg-accent', title: 'Auto-reschedule', desc: 'Missed, added, or edited a task? Scedly recomputes incrementally and protects rigid time.' },
    { icon: '✶', color: 'bg-coin', title: 'Conflict resolution', desc: 'Overlaps get resolved automatically when safe, escalated to you with clear options when not.' },
    { icon: '◷', color: 'bg-pri-low', title: 'Working windows & focus hours', desc: 'Set when you work and when you focus. Low-priority tasks stay out of protected time.' },
    { icon: '∞', color: 'bg-accent-2', title: 'Behavioral learning', desc: 'It notices patterns over weeks and nudges: "You skip gym on Thursdays 4/5 times — move it?"' },
    { icon: '⌘', color: 'bg-coin', title: 'Everywhere you work', desc: 'Web, CLI, Slack, Telegram, Google Chat, MCP — one brain, one set of data, in sync.' },
  ];
  return (
    <section id="features" className="py-24">
      <div className="max-w-content mx-auto px-6">
        <div className="text-center">
          <span className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">Features</span>
          <h2 className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">A scheduler with a memory.</h2>
        </div>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={stagger} className="grid md:grid-cols-3 gap-5 mt-12">
          {items.map(f => (
            <motion.div key={f.title} variants={fadeUp} className="bg-surface border border-border rounded-card p-5 hover:-translate-y-1 hover:border-border-strong hover:shadow-card transition-all">
              <div className={`w-6 h-6 rounded ${f.color} grid place-items-center text-xs font-bold text-[#04121f] shadow-[inset_-3px_-3px_0_rgba(0,0,0,.22),inset_3px_3px_0_rgba(255,255,255,.28)]`}>{f.icon}</div>
              <h3 className="mt-4 text-lg font-semibold text-text-primary">{f.title}</h3>
              <p className="mt-2 text-sm text-text-secondary">{f.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function AILearns() {
  return (
    <section className="py-24 bg-bg-elev border-y border-border">
      <div className="max-w-content mx-auto px-6 grid md:grid-cols-2 gap-12 items-center">
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={stagger}>
          <motion.span variants={fadeUp} className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">It compounds</motion.span>
          <motion.h2 variants={fadeUp} className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">The longer you use it, the smarter it gets.</motion.h2>
          <motion.p variants={fadeUp} className="mt-4 text-lg text-text-secondary">Scedly builds a private memory of how you actually work — and turns it into better scheduling, not just records.</motion.p>
          <motion.ul variants={fadeUp} className="mt-6 flex flex-col gap-3">
            {['Week 1 · learns your durations & peak hours','Week 3 · spots recurring skips & best times','Month 2 · proactively coaches your week'].map(t => (
              <li key={t} className="inline-flex items-center w-fit px-3 py-1.5 rounded-lg border border-border bg-surface text-sm text-text-secondary">{t}</li>
            ))}
          </motion.ul>
        </motion.div>
        <motion.div initial={{ opacity: 0, x: 20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 }}>
          <TerminalWindow title="scedly — insights">
            <div className="text-term-dim">{'// after 4 weeks of history'}</div>
            <div className="text-accent">◔ You complete deep work 30% faster before noon.</div>
            <div className="text-accent">◔ Gym skipped 4/5 Thursdays.</div>
            <Line usr mt>add gym thursday</Line>
            <div className="text-pri-med mt-2">💡 You usually skip gym on Thursday. Want Wednesday 18:00 instead?</div>
            <div className="text-term-dim">  [ yes ]  [ keep thursday ]</div>
          </TerminalWindow>
        </motion.div>
      </div>
    </section>
  );
}

function Channels() {
  const channels = [
    { icon: '🖥️', name: 'Web app', desc: 'Terminal-style dashboard' },
    { icon: '⌨️', name: 'CLI', desc: 'pip install scedly' },
    { icon: '💬', name: 'Slack', desc: 'Schedule in-thread' },
    { icon: '✈️', name: 'Telegram', desc: 'On your phone' },
    { icon: '🗨️', name: 'Google Chat', desc: 'In your workspace' },
    { icon: '🤖', name: 'MCP', desc: 'Claude Code / Cursor' },
    { icon: '📅', name: 'Calendar sync', desc: 'Google & Outlook' },
    { icon: '✉️', name: 'Email', desc: 'Daily summaries' },
  ];
  return (
    <section id="channels" className="py-24">
      <div className="max-w-content mx-auto px-6 text-center">
        <span className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">One brain, every surface</span>
        <h2 className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">Manage your day from anywhere.</h2>
        <p className="mt-4 text-lg text-text-secondary mx-auto max-w-[56ch]">A task created in your terminal shows up on your calendar instantly — and vice versa.</p>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={stagger} className="grid grid-cols-2 md:grid-cols-4 gap-5 mt-12">
          {channels.map(c => (
            <motion.div key={c.name} variants={fadeUp} className="bg-surface border border-border rounded-card p-5 text-center">
              <div className="text-2xl">{c.icon}</div>
              <h3 className="mt-2 text-base font-semibold text-text-primary">{c.name}</h3>
              <p className="mt-2 text-xs text-text-secondary font-mono">{c.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function CLISection() {
  return (
    <section id="cli" className="py-24">
      <div className="max-w-content mx-auto px-6 grid md:grid-cols-[0.92fr_1.08fr] gap-12 items-center">
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={stagger}>
          <motion.span variants={fadeUp} className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">For the terminal-native</motion.span>
          <motion.h2 variants={fadeUp} className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">Never leave your terminal.</motion.h2>
          <motion.p variants={fadeUp} className="mt-4 text-lg text-text-secondary">Scedly ships a tiny pip-installable CLI — a pure HTTP client to the same backend. Schedule, stream replies token-by-token, and check your day without touching the browser.</motion.p>
          <motion.div variants={fadeUp} className="flex flex-col gap-3 mt-6">
            {[
              'scedly login — paste your API key once',
              'scedly chat "…" — talk to the agent, streamed',
              'scedly schedule — today\'s blocks',
              'scedly tasks --status all — your list',
            ].map(c => <span key={c} className="inline-flex w-fit px-3 py-1.5 rounded-lg border border-border bg-surface text-sm text-text-secondary font-mono">{c}</span>)}
          </motion.div>
          <motion.p variants={fadeUp} className="mt-6 font-mono text-xs text-text-tertiary">Included with Pro & during your 14-day trial. Same data as web, Slack & MCP.</motion.p>
        </motion.div>
        <motion.div initial={{ opacity: 0, x: 20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 }}>
          <TerminalWindow title="bash — scedly">
            <div className="text-term-dim">$ pip install scedly</div>
            <div className="text-term-dim">$ scedly</div>
            <div className="text-[#e0a93c]">{'          \\   |   /'}</div>
            <div><span className="text-[#e0a93c]">{"       '-. "}</span><span className="text-[#ffd75f]">.-~-.</span><span className="text-[#e0a93c]">{" .-'"}</span></div>
            <div><span className="text-[#e0a93c]">{"     ---  "}</span><span className="text-[#ffd75f]">( o o )</span><span className="text-[#e0a93c]">{"  ---     "}</span><span className="text-pri-low">scedly_</span></div>
            <div><span className="text-[#e0a93c]">{"       .-' "}</span><span className="text-[#ffd75f]">{"'-_-'"}</span><span className="text-[#e0a93c]">{" '-.      schedule, automated."}</span></div>
            <div className="text-[#e0a93c]">{'          /   |   \\'}</div>
            <div>&nbsp;</div>
            <div className="text-term-dim">$ scedly login</div>
            <div>API key (sk-...): <span className="text-term-dim">••••••••••••</span></div>
            <div className="text-pri-low">✓ Logged in. Config saved.</div>
            <div>&nbsp;</div>
            <div><span className="text-term-dim">$</span> <span className="text-[#e7edf4]">scedly chat &quot;draft the investor update, 2h, due friday&quot;</span></div>
            <div>Scheduled <span className="text-pri-low">&quot;Investor update&quot;</span> for Thu 09:00–11:00 — placed in your</div>
            <div>morning focus block with a full day of buffer before the deadline.<span className="inline-block w-2 h-[1.05em] bg-term-green align-[-2px] animate-blink" /></div>
            <div>&nbsp;</div>
            <div><span className="text-term-dim">$</span> <span className="text-[#e7edf4]">scedly schedule</span></div>
            <div>  09:00 – 11:00  Investor update</div>
            <div>  13:30 – 13:45  Standup notes</div>
            <div>  15:00 – 15:45  Review PR #482</div>
          </TerminalWindow>
        </motion.div>
      </div>
    </section>
  );
}

function MCPSection() {
  return (
    <section id="mcp" className="py-24 bg-bg-elev border-y border-border">
      <div className="max-w-content mx-auto px-6">
        <div className="text-center">
          <span className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">MCP · your AI agent, our data</span>
          <h2 className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">Schedule from inside Claude Code & Cursor.</h2>
          <p className="mt-4 text-lg text-text-secondary mx-auto max-w-[56ch]">Scedly exposes an MCP server, so your coding agent can create tasks, pull your day, and reschedule — without you ever leaving the editor.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-5 mt-12">
          <TerminalWindow title="claude code — mcp: scedly">
            <Line usr>before I start the auth refactor, block 2 focused hours tomorrow</Line>
            <div className="text-term-dim mt-2">Claude is using a tool…</div>
            <div><span className="text-accent-2">⚙ scedly.create_task</span> <span className="text-term-dim">{'{ title:"Auth refactor", duration:120, energy:"High" }'}</span></div>
            <div className="text-pri-low">  → ✓ scheduled Fri 09:00–11:00</div>
            <div className="mt-2">Reserved tomorrow morning — your peak focus window — for the refactor. I&apos;ll start on the code now.<span className="inline-block w-2 h-[1.05em] bg-term-green align-[-2px] animate-blink" /></div>
          </TerminalWindow>
          <TerminalWindow title="cursor — mcp: scedly">
            <Line usr>what&apos;s left today? reschedule if I&apos;m behind</Line>
            <div className="mt-2"><span className="text-accent-2">⚙ scedly.get_schedule</span><span className="text-term-dim">()</span> <span className="text-pri-low">→ 3 tasks</span></div>
            <div><span className="text-accent-2">⚙ scedly.reschedule</span><span className="text-term-dim">(missed=&quot;standup&quot;)</span> <span className="text-pri-med">→ moved</span></div>
            <div className="mt-2">Updated your day:</div>
            <div className="text-term-dim">  15:30  Standup notes   (was 09:30)</div>
            <div className="text-term-dim">  16:00  Review PR #482</div>
            <div>You&apos;re back on track.<span className="inline-block w-2 h-[1.05em] bg-term-green align-[-2px] animate-blink" /></div>
          </TerminalWindow>
        </div>
        <div className="flex flex-wrap justify-center gap-3 mt-8">
          {['create_task','list_tasks','get_schedule','reschedule','mark_complete','update_preferences'].map(c => (
            <span key={c} className="px-3 py-1.5 rounded-lg border border-border bg-surface font-mono text-sm text-text-secondary">{c}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  return (
    <section id="pricing" className="py-24 bg-bg-elev border-y border-border">
      <div className="max-w-content mx-auto px-6">
        <div className="text-center">
          <span className="font-mono text-xs tracking-[.18em] uppercase text-accent inline-flex items-center gap-2 before:content-[''] before:w-4 before:h-0.5 before:bg-accent before:inline-block">Pricing</span>
          <h2 className="mt-4 text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">14 days of Pro, free. No card.</h2>
          <p className="mt-4 text-lg text-text-secondary mx-auto max-w-[56ch]">Every new account starts on a <strong className="text-text-primary">14-day Pro trial</strong> — all features, all channels, no credit card. When it ends you simply roll onto the Free plan.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-5 mt-12 max-w-[820px] mx-auto">
          <div className="bg-surface border border-border rounded-card p-6">
            <h3 className="font-mono text-lg font-bold text-text-primary">Free</h3>
            <div className="flex items-baseline gap-2 mt-2"><span className="text-4xl font-extrabold text-text-primary">$0</span><span className="text-text-secondary">/forever</span></div>
            <p className="mt-2 text-sm text-text-secondary">Where you land after the trial.</p>
            <Link href="/login" className="mt-6 w-full inline-flex justify-center px-4 py-2.5 rounded-lg border border-border bg-surface-2 text-text-primary text-sm font-semibold hover:bg-surface-3 transition-colors">Start free trial</Link>
            <ul className="mt-6 flex flex-col gap-3 font-mono text-sm text-text-secondary">
              <li>✓ 30 tasks / month</li>
              <li>✓ Web app dashboard</li>
              <li>✓ AI scheduling & rescheduling</li>
              <li className="text-text-tertiary">✗ CLI, Slack, Telegram, MCP</li>
              <li className="text-text-tertiary">✗ Calendar sync & email</li>
            </ul>
          </div>
          <div className="bg-surface border-2 border-accent rounded-card p-6 relative shadow-[0_0_0_1px_#5bb8ff,0_8px_28px_-8px_rgba(0,0,0,.6)]">
            <span className="absolute -top-3 right-5 px-2.5 py-1 rounded-full bg-accent text-[#04121f] font-mono text-xs font-bold">14-day free trial</span>
            <h3 className="font-mono text-lg font-bold text-text-primary">Pro</h3>
            <div className="flex items-baseline gap-2 mt-2"><span className="text-4xl font-extrabold text-text-primary">$9</span><span className="text-text-secondary">/mo · or $96/yr</span></div>
            <p className="mt-2 text-sm text-text-secondary">Free for 14 days, then $9/mo if you keep it.</p>
            <Link href="/login" className="mt-6 w-full inline-flex justify-center px-4 py-2.5 rounded-lg bg-accent text-[#04121f] text-sm font-semibold shadow-[0_6px_18px_-6px_#5bb8ff] hover:brightness-110 transition-all">Start 14-day trial</Link>
            <ul className="mt-6 flex flex-col gap-3 font-mono text-sm text-text-secondary">
              <li>✓ Unlimited tasks</li>
              <li>✓ All channels — CLI, Slack, Telegram, Google Chat, MCP</li>
              <li>✓ Google & Outlook calendar sync</li>
              <li>✓ Email reminders & daily summaries</li>
              <li>✓ Behavioral coaching & priority routing</li>
            </ul>
          </div>
        </div>
        <p className="text-center font-mono text-xs text-text-tertiary mt-6">Secure payments by Stripe. Cancel anytime from the billing portal.</p>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="py-24 text-center">
      <div className="max-w-content mx-auto px-6">
        <h2 className="text-[clamp(1.7rem,3.2vw,2.5rem)] font-[680] leading-[1.12] tracking-tight text-text-primary">Stop managing your calendar.<br />Let it manage itself.</h2>
        <Link href="/login" className="mt-6 inline-flex px-6 py-3 rounded-lg bg-accent text-[#04121f] font-semibold shadow-[0_6px_18px_-6px_#5bb8ff] hover:brightness-110 transition-all">Get started free →</Link>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-border py-12">
      <div className="max-w-content mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-[1.6fr_1fr_1fr_1fr] gap-8">
          <div>
            <Link href="/" className="flex items-center gap-2.5">
              <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#2b3550] to-[#1a2236] grid place-items-center text-sm shadow-[0_0_0_1px_rgba(255,255,255,.06)_inset,0_4px_16px_-6px_#5bb8ff]">🌙</span>
              <span className="font-mono font-bold text-text-primary">scedly<span className="text-term-green animate-blink">_</span></span>
            </Link>
            <p className="mt-4 text-sm text-text-secondary max-w-[30ch]">The AI behavioral coach that uses your calendar as its interface.</p>
          </div>
          <div>
            <h4 className="text-xs uppercase tracking-widest text-text-tertiary mb-3">Product</h4>
            {['Features','Channels','Pricing','Dashboard'].map(l => <a key={l} href="#" className="block text-sm text-text-secondary py-1 hover:text-text-primary">{l}</a>)}
          </div>
          <div>
            <h4 className="text-xs uppercase tracking-widest text-text-tertiary mb-3">Access</h4>
            {['CLI','Slack','Telegram','MCP server'].map(l => <a key={l} href="#" className="block text-sm text-text-secondary py-1 hover:text-text-primary">{l}</a>)}
          </div>
          <div>
            <h4 className="text-xs uppercase tracking-widest text-text-tertiary mb-3">Account</h4>
            {['Sign in','Onboarding','Settings'].map(l => <a key={l} href="#" className="block text-sm text-text-secondary py-1 hover:text-text-primary">{l}</a>)}
          </div>
        </div>
        <div className="h-px bg-border mt-8" />
        <div className="flex flex-col items-center gap-3 pt-6 pb-2">
          <span className="text-xs uppercase tracking-widest text-text-tertiary">Connect with the founder</span>
          <div className="flex items-center gap-4">
            <a href="https://www.linkedin.com/in/medhansh-narang-188760391/" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-[var(--accent)] transition-colors">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
              LinkedIn
            </a>
            <a href="mailto:medhanshnarang2407@gmail.com" className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-[var(--accent)] transition-colors">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              medhanshnarang2407@gmail.com
            </a>
          </div>
        </div>
        <div className="h-px bg-border mt-4" />
        <div className="flex flex-wrap justify-between gap-3 pt-5">
          <span className="font-mono text-xs text-text-tertiary">© A.K.A. All rights reserved.</span>
          <span className="font-mono text-xs text-text-tertiary">scedly_ · built for founders who ship</span>
        </div>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  const { theme, toggle } = useTheme();
  return (
    <div className={theme === 'light' ? 'landing-light' : 'landing-dark'} style={{
      '--bg': theme === 'dark' ? '#0a0c10' : '#faf8f3',
      '--bg-elev': theme === 'dark' ? '#0e1118' : '#ffffff',
      '--surface': theme === 'dark' ? '#12161f' : '#ffffff',
      '--surface-2': theme === 'dark' ? '#161b26' : '#f6f3ec',
      '--surface-3': theme === 'dark' ? '#1b212e' : '#efeadf',
      '--border': theme === 'dark' ? '#232a37' : '#e7e1d4',
      '--border-strong': theme === 'dark' ? '#303a4b' : '#d8d0bd',
      '--text': theme === 'dark' ? '#e7edf4' : '#1b1f27',
      '--text-muted': theme === 'dark' ? '#8b97a8' : '#5d6470',
      '--text-faint': theme === 'dark' ? '#5c6675' : '#939aa6',
      '--term-green': theme === 'dark' ? '#6ee7a0' : '#1f8a52',
      '--term-dim': theme === 'dark' ? '#4a6a57' : '#5b7d6a',
      '--term-bg': theme === 'dark' ? '#07090d' : '#1d2230',
      '--accent': theme === 'dark' ? '#5bb8ff' : '#2f7fe0',
      '--accent-2': theme === 'dark' ? '#8b7dff' : '#6a5cf0',
      '--pri-high': theme === 'dark' ? '#ef5350' : '#e23b36',
      '--pri-med': theme === 'dark' ? '#ffc93c' : '#d99500',
      '--pri-low': theme === 'dark' ? '#4cc38a' : '#1f9d63',
      '--coin': theme === 'dark' ? '#ffc93c' : '#e0a400',
      '--logo-from': theme === 'dark' ? '#2b3550' : '#ffc93c',
      '--logo-to': theme === 'dark' ? '#1a2236' : '#ff9d3c',
      '--logo-shadow': theme === 'dark' ? '0 0 0 1px rgba(255,255,255,.06) inset,0 4px 16px -6px #5bb8ff' : '0 0 0 1px rgba(0,0,0,.25) inset,0 4px 14px -4px #ffc93c',
    } as React.CSSProperties}>
      <div className="min-h-screen bg-[var(--bg)] text-[var(--text)] transition-colors duration-200" style={{ backgroundImage: theme === 'dark' ? 'radial-gradient(rgba(255,255,255,0.022) 1px,transparent 1px)' : 'radial-gradient(rgba(0,0,0,0.03) 1px,transparent 1px)', backgroundSize: '28px 28px', backgroundAttachment: 'fixed' }}>
        <Nav theme={theme} toggle={toggle} />
        <Hero />
        <ChannelStrip />
        <Problem />
        <HowItWorks />
        <Features />
        <AILearns />
        <Channels />
        <CLISection />
        <MCPSection />
        <Pricing />
        <CTA />
        <Footer />
      </div>
    </div>
  );
}
