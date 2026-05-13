"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Footer from "@/components/marketing/footer";
import Nav from "@/components/marketing/nav";
import { ArrowRight, Check, Zap, Shield, ChevronDown, GitBranch, Activity, Search, Database, RefreshCw, Clock, ChevronUp, Bot, Globe, FileText } from "lucide-react";

// --- Telegram SVG ---
const TelegramIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
  </svg>
);

// --- Discord SVG ---
const DiscordIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057.1 18.082.114 18.106.133 18.122a19.891 19.891 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
  </svg>
);

// --- Animated node grid background ---
const SystemGrid = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const nodes: { x: number; y: number; vx: number; vy: number; pulse: number }[] = [];
    const count = 28;

    for (let i = 0; i < count; i++) {
      nodes.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        pulse: Math.random() * Math.PI * 2,
      });
    }

    let animId: number;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      nodes.forEach(n => {
        n.x += n.vx;
        n.y += n.vy;
        n.pulse += 0.02;
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
      });

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 180) {
            const alpha = (1 - dist / 180) * 0.12;
            ctx.beginPath();
            ctx.strokeStyle = `rgba(251, 80, 5, ${alpha})`;
            ctx.lineWidth = 0.8;
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }
      }

      nodes.forEach(n => {
        const glow = (Math.sin(n.pulse) + 1) / 2;
        ctx.beginPath();
        ctx.arc(n.x, n.y, 2 + glow, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(251, 80, 5, ${0.3 + glow * 0.4})`;
        ctx.fill();
      });

      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />;
};

const systemLogs = [
  'Raven completed: Invoice dispatch — 8 sent',
  'Raven completed: Lead follow-up — 12 contacts',
  'Raven completed: Competitor price scan — 3 changes flagged',
  'Raven completed: Notion sync — 47 records updated',
  'Raven completed: Weekly status report — delivered to Slack',
  'Raven completed: GitHub issue triage — 9 items labeled',
];

// --- Hero System Log Ticker ---
const SystemLogTicker = () => {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % systemLogs.length), 4500);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex items-center gap-2.5 bg-[#0F0F0E]/80 rounded px-3.5 py-2 backdrop-blur-sm max-w-sm">
      <span className="w-1.5 h-1.5 rounded-full bg-[#1AC153] flex-shrink-0 status-blink" />
      <span className="text-[#E7E6E6]/50 font-mono text-[10px] leading-relaxed ticker-anim truncate">{systemLogs[idx]}</span>
    </div>
  );
};

// --- Hero ---
const Hero = () => (
  <section className="relative min-h-screen flex flex-col overflow-hidden bg-[#080808]">
    <SystemGrid />

    <div className="absolute inset-0 pointer-events-none"
      style={{backgroundImage: 'linear-gradient(rgba(251,80,5,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(251,80,5,0.025) 1px, transparent 1px)', backgroundSize: '80px 80px'}} />

    <div className="scan-line-hero" style={{animationDelay: '1.5s'}} />

    <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#080808] to-transparent pointer-events-none z-10" />

    <div className="absolute top-20 left-6 z-20 flex items-center gap-2 opacity-40">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="flex-shrink-0">
        <line x1="6" y1="0" x2="6" y2="5" stroke="#FB5005" strokeWidth="1"/>
        <line x1="6" y1="7" x2="6" y2="12" stroke="#FB5005" strokeWidth="1"/>
        <line x1="0" y1="6" x2="5" y2="6" stroke="#FB5005" strokeWidth="1"/>
        <line x1="7" y1="6" x2="12" y2="6" stroke="#FB5005" strokeWidth="1"/>
      </svg>
      <span className="font-mono text-[9px] text-[#FB5005]/70 tracking-widest uppercase">SYS.NODE</span>
    </div>

    <div className="absolute top-20 right-6 z-20 flex flex-col items-end gap-1 opacity-35 pointer-events-none">
      <div className="flex items-center gap-1.5">
        <span className="w-1 h-1 rounded-full bg-[#1AC153] status-blink" />
        <span className="font-mono text-[9px] text-[#1AC153]/80 tracking-widest uppercase">STATUS: ONLINE</span>
      </div>
      <span className="font-mono text-[9px] text-white/30 tracking-widest">NODES: 12,746</span>
      <span className="font-mono text-[9px] text-white/30 tracking-widest">UPTIME: 99.99%</span>
    </div>

    <div className="absolute bottom-20 left-6 z-20 flex flex-col gap-0.5 opacity-25 pointer-events-none">
      {['0', '01', '10', '100'].map(n => (
        <span key={n} className="font-mono text-[8px] text-[#FB5005]/60">{n}</span>
      ))}
      <div className="w-px h-8 bg-[#FB5005]/20 mt-1" />
    </div>

    <div className="absolute bottom-20 right-6 z-20 opacity-25 pointer-events-none">
      <div className="flex items-center gap-1.5 mb-1">
        <div className="w-6 h-px bg-[#FB5005]/40" />
        <span className="font-mono text-[8px] text-white/30 tracking-widest">ARC-V3</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-3 h-px bg-[#FB5005]/20" />
        <span className="font-mono text-[8px] text-white/20 tracking-widest">LIVE</span>
      </div>
    </div>

    <div className="relative z-10 flex-1 flex items-center">
      <div className="max-w-7xl mx-auto px-6 lg:px-10 w-full pt-24 pb-8">
        <div className="grid lg:grid-cols-2 gap-8 lg:gap-4 items-center min-h-[75vh]">

          <div className="flex flex-col justify-center lg:pr-8">
            <div className="inline-flex items-center gap-2 border border-[#FB5005]/25 rounded-full px-3.5 py-1.5 mb-10 w-fit">
              <span className="w-1.5 h-1.5 rounded-full bg-[#FB5005] status-blink" />
              <span className="text-[#FB5005]/80 text-[10px] font-mono tracking-widest uppercase">Your first autonomous team member</span>
            </div>

            <h1 className="font-heading font-normal text-[#E7E6E6] leading-[1.04] mb-6"
              style={{fontSize: 'clamp(2.8rem, 6vw, 5.5rem)'}}>
              Raven runs your<br />operations.
            </h1>

            <p className="text-[#E7E6E6]/55 font-body text-base lg:text-lg max-w-lg mb-4 leading-relaxed">
              You are doing work that should run itself. Research. Data entry. Status updates. Follow-ups. ArcLink deploys autonomous agents that handle the repetition — so you focus on decisions that matter.
            </p>
            <p className="text-[#E7E6E6]/30 font-mono text-xs mb-10 tracking-wide">
              Raven gets your first agent operational in minutes.
            </p>

            <div className="flex flex-col sm:flex-row gap-3 mb-10">
              <Link href="/onboarding?channel=telegram" className="flex items-center gap-3 bg-[#FB5005] hover:bg-[#e04504] text-white font-body font-semibold px-6 py-3.5 rounded transition-all hover:shadow-[0_0_28px_rgba(251,80,5,0.4)] w-full sm:w-auto justify-center text-sm">
                <TelegramIcon /> START WITH TELEGRAM
              </Link>
              <Link href="/onboarding?channel=discord" className="flex items-center gap-3 bg-transparent hover:bg-white/5 border border-white/20 hover:border-white/35 text-[#E7E6E6] font-body font-semibold px-6 py-3.5 rounded transition-all w-full sm:w-auto justify-center text-sm">
                <DiscordIcon /> START WITH DISCORD
              </Link>
            </div>

            <SystemLogTicker />
          </div>

          <div className="relative flex items-center justify-center lg:justify-end">
            <div className="raven-scan-line" style={{animationDelay: '0s'}} />

            <div className="absolute inset-0 pointer-events-none"
              style={{background: 'radial-gradient(ellipse 70% 60% at 60% 50%, rgba(251,80,5,0.07) 0%, transparent 70%)'}} />

            <div className="absolute top-4 left-4 lg:left-8 opacity-30 pointer-events-none z-30">
              <div className="w-5 h-5 border-t border-l border-[#FB5005]/60" />
            </div>
            <div className="absolute bottom-4 right-4 opacity-30 pointer-events-none z-30">
              <div className="w-5 h-5 border-b border-r border-[#FB5005]/60" />
            </div>

            <div className="absolute top-4 right-4 z-30 opacity-30 pointer-events-none">
              <span className="font-mono text-[8px] text-[#FB5005]/70 tracking-widest uppercase">RAVEN / OPERATOR</span>
            </div>

            <div className="relative w-full max-w-xl lg:max-w-none" style={{filter: 'drop-shadow(0 0 40px rgba(251,80,5,0.12)) drop-shadow(0 0 80px rgba(251,80,5,0.06))'}}>
              <Image
                src="/marketing/raven-hero1.png"
                alt="Raven — ArcLink AI Operator"
                width={1254}
                height={1254}
                className="w-full h-auto object-contain select-none"
                style={{
                  maxHeight: '72vh',
                  opacity: 1,
                  mixBlendMode: 'multiply',
                }}
                sizes="(max-width: 1024px) 90vw, 50vw"
                unoptimized
                priority
                draggable={false}
              />
              <div className="absolute pointer-events-none eye-pulse-dot"
                style={{top: '38%', left: '58%', width: '8px', height: '8px',
                  borderRadius: '50%', background: 'radial-gradient(circle, #FB5005 0%, rgba(251,80,5,0.4) 60%, transparent 100%)',
                  boxShadow: '0 0 14px 5px rgba(251,80,5,0.55)'}}>
              </div>
            </div>

            <div className="absolute right-0 top-1/2 -translate-y-1/2 flex flex-col gap-3 opacity-20 pointer-events-none z-30">
              {[0,1,2,3,4].map(i => (
                <div key={i} className={`bg-[#FB5005]/50 ${i === 2 ? 'w-3 h-px' : 'w-1.5 h-px'}`} />
              ))}
            </div>
          </div>
        </div>

        <div className="border-t border-white/5 pt-8 mt-2">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
            {[
              { value: '12.7K+', label: 'NODES' },
              { value: '99.99%', label: 'UPTIME' },
              { value: '256-BIT', label: 'ENCRYPTION' },
              { value: '24/7', label: 'MONITORING' },
            ].map((stat, i) => (
              <div key={i} className="flex flex-col gap-1">
                <span className="font-heading font-bold text-[#FB5005] text-2xl lg:text-3xl leading-none">{stat.value}</span>
                <span className="font-mono text-[9px] text-[#E7E6E6]/30 tracking-widest uppercase">{stat.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>

    <a href="#problem" className="absolute bottom-6 left-1/2 -translate-x-1/2 text-[#E7E6E6]/20 animate-bounce z-20">
      <ChevronDown size={20} />
    </a>
  </section>
);

// --- Integrations Carousel ---
const integrations = [
  {
    name: 'Notion',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.934zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.14c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z"/>
      </svg>
    ),
  },
  {
    name: 'GitHub',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
      </svg>
    ),
  },
  {
    name: 'Slack',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/>
      </svg>
    ),
  },
  {
    name: 'Google',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
      </svg>
    ),
  },
  {
    name: 'HubSpot',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M18.164 7.931V5.085a2.198 2.198 0 0 0 1.266-1.978V3.07a2.198 2.198 0 0 0-2.196-2.196h-.037a2.198 2.198 0 0 0-2.196 2.196v.037a2.198 2.198 0 0 0 1.266 1.978v2.846a6.232 6.232 0 0 0-2.963 1.305L6.862 4.485a2.44 2.44 0 0 0 .071-.571 2.46 2.46 0 1 0-2.46 2.46c.472 0 .912-.135 1.285-.368l8.346 4.813a6.232 6.232 0 0 0-.872 3.208 6.232 6.232 0 0 0 1.08 3.496l-2.532 2.532a1.89 1.89 0 0 0-.55-.085 1.9 1.9 0 1 0 1.9 1.9 1.89 1.89 0 0 0-.085-.55l2.5-2.5a6.237 6.237 0 1 0 2.619-10.89zm-.967 9.274a3.44 3.44 0 1 1 0-6.88 3.44 3.44 0 0 1 0 6.88z"/>
      </svg>
    ),
  },
  {
    name: 'Airtable',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M11.955.592L.592 4.922a.72.72 0 0 0 .004 1.343l11.38 4.21a2.16 2.16 0 0 0 1.507 0l11.38-4.21a.72.72 0 0 0 .004-1.343L13.505.592a2.16 2.16 0 0 0-1.55 0zM.71 8.649A.72.72 0 0 0 0 9.38v9.589a.72.72 0 0 0 .984.671l10.08-3.73a.72.72 0 0 0 .456-.671V5.65a.72.72 0 0 0-.984-.671L.71 8.649zm22.58 0l-10.08-3.67a.72.72 0 0 0-.984.671v9.589a.72.72 0 0 0 .456.671l10.08 3.73A.72.72 0 0 0 24 18.97V9.38a.72.72 0 0 0-.71-.731z"/>
      </svg>
    ),
  },
  {
    name: 'Zapier',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M14.974 8.974l-.024.038-2.948 4.97H16.5a.5.5 0 0 1 .5.5v.018c-.003 2.37-.636 4.689-1.82 6.718l-.03.053-1.404-1.404a.5.5 0 0 0-.707.707l1.416 1.415c-1.404 1.99-3.397 3.507-5.718 4.238l-.217.065V21.5a.5.5 0 0 0-1 0v3.792c-2.55-.773-4.734-2.394-6.213-4.55l1.39-1.39a.5.5 0 0 0-.707-.707L1.576 19.96C.529 18.07 0 15.927 0 13.5v-.018a.5.5 0 0 1 .5-.5h4.499l-2.975-5.01a.505.505 0 0 1 .07-.602l.012-.012C3.62 5.35 5.96 4.31 8.5 4.31c.44 0 .875.032 1.3.094V.5a.5.5 0 0 1 1 0v3.904c.425-.062.86-.094 1.3-.094 2.54 0 4.88 1.04 6.394 2.858l.013.012a.505.505 0 0 1 .07.602l-.603 1.192z"/>
      </svg>
    ),
  },
  {
    name: 'Stripe',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.654 6.104 1.872 4.56 3.147 3.757 4.992 3.757 7.218c0 4.039 2.467 5.76 6.476 7.219 2.585.92 3.445 1.574 3.445 2.583 0 .98-.84 1.545-2.354 1.545-1.875 0-4.965-.921-6.99-2.109l-.9 5.555C4.532 23.175 7.595 24 11.08 24c2.643 0 4.872-.567 6.413-1.637 1.649-1.133 2.507-2.936 2.507-5.2 0-4.098-2.498-5.799-6.024-7.013z"/>
      </svg>
    ),
  },
  {
    name: 'OpenAI',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"/>
      </svg>
    ),
  },
  {
    name: 'Telegram',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
      </svg>
    ),
  },
  {
    name: 'Discord',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057.1 18.082.114 18.106.133 18.122a19.891 19.891 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
      </svg>
    ),
  },
  {
    name: 'Webhooks',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M15.73 3.11c-1.61.37-2.82 1.75-2.99 3.38-.08.77.06 1.51.37 2.15L9.18 13.8a3.61 3.61 0 0 0-1.16-.19c-2 0-3.62 1.62-3.62 3.62s1.62 3.62 3.62 3.62 3.62-1.62 3.62-3.62c0-.54-.12-1.05-.33-1.51l3.88-5.15a3.46 3.46 0 0 0 2.19.11 3.64 3.64 0 0 0 2.57-4.45 3.637 3.637 0 0 0-4.22-2.63zM8.02 19.49c-.7 0-1.27-.57-1.27-1.27s.57-1.27 1.27-1.27 1.27.57 1.27 1.27-.57 1.27-1.27 1.27zm8.11-10.56c-.7 0-1.27-.57-1.27-1.27s.57-1.27 1.27-1.27 1.27.57 1.27 1.27-.57 1.27-1.27 1.27zm-1.64 3.39l-2.33 3.1c-.27-.05-.55-.08-.83-.08-.43 0-.85.08-1.23.22l-1.83-2.43c.36-.52.57-1.15.57-1.83 0-.32-.05-.63-.14-.92l3.89-1.41c.33.66.85 1.2 1.5 1.56l.4 1.79z"/>
      </svg>
    ),
  },
  {
    name: 'Jira',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.762a1.005 1.005 0 0 0-1.001-1.005zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24.018 12.49V1.005A1.001 1.001 0 0 0 23.013 0z"/>
      </svg>
    ),
  },
  {
    name: 'Salesforce',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M10.005 4.117c.838-.87 2.006-1.413 3.3-1.413 1.72 0 3.22.959 4.016 2.383a5.06 5.06 0 0 1 2.008-.415c2.818 0 5.1 2.296 5.1 5.13 0 2.833-2.282 5.13-5.1 5.13-.343 0-.677-.035-1-.1a3.87 3.87 0 0 1-3.447 2.112 3.87 3.87 0 0 1-1.578-.336 4.497 4.497 0 0 1-4.267 3.076A4.509 4.509 0 0 1 4.53 15.8a3.96 3.96 0 0 1-.63.05C1.747 15.851 0 14.095 0 11.93c0-1.458.774-2.734 1.93-3.432a4.07 4.07 0 0 1-.244-1.393C1.686 4.939 3.612 3 5.98 3c1.64 0 3.068.913 3.79 2.259a4.528 4.528 0 0 1 .235-1.142z"/>
      </svg>
    ),
  },
  {
    name: 'Gmail',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z"/>
      </svg>
    ),
  },
  {
    name: 'Trello',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M21 0H3C1.343 0 0 1.343 0 3v18c0 1.656 1.343 3 3 3h18c1.656 0 3-1.344 3-3V3c0-1.657-1.344-3-3-3zM10.44 18.18c0 .795-.645 1.44-1.44 1.44H4.56c-.795 0-1.44-.645-1.44-1.44V4.56c0-.795.645-1.44 1.44-1.44H9c.795 0 1.44.645 1.44 1.44v13.62zm10.44-6c0 .794-.645 1.44-1.44 1.44H15c-.795 0-1.44-.646-1.44-1.44V4.56c0-.795.645-1.44 1.44-1.44h4.44c.795 0 1.44.645 1.44 1.44v7.62z"/>
      </svg>
    ),
  },
  {
    name: 'Linear',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M.338 13.698C1.98 18.9 6.68 22.74 12.28 22.74c.26 0 .52-.006.777-.018L.338 13.698zm-.267-1.498l11.82 11.82A12.004 12.004 0 0 1 .071 12.2zM12 0C5.373 0 0 5.373 0 12c0 .22.006.44.018.657L11.343.331A12.04 12.04 0 0 1 12 0zm1.32.113L.113 13.32A12.002 12.002 0 0 1 12 0c.449 0 .89.024 1.32.113zM24 12c0 6.627-5.373 12-12 12a11.95 11.95 0 0 1-7.62-2.742l16.88-16.88A11.95 11.95 0 0 1 24 12zm-.118-1.32A11.998 11.998 0 0 1 23.887 12L12 23.887a12.002 12.002 0 0 1-1.207-11.207z"/>
      </svg>
    ),
  },
  {
    name: 'Shopify',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M15.337.009s-.187.055-.5.163c-.307-.883-.853-1.697-1.807-1.697h-.084C12.6-2.23 12.257-2.494 11.97-2.494c-2.04 0-3.02 2.548-3.328 3.845-.796.246-1.713.53-2.634.814-.8.247-1.6.494-2.4.741L2.45 16.638 15.99 19 24 17.32 21.337.009h-6zM14.47.574c-.007.006-.008.01-.014.018A4.82 4.82 0 0 0 13.64.37c.012-.013.022-.028.035-.04a.888.888 0 0 1 .796-.357zm-2.5-.33c.258 0 .464.076.633.215-.816.384-1.655 1.19-1.96 2.992-.476.148-.947.294-1.395.433.34-1.173 1.136-3.64 2.722-3.64zm1.246 9.04l-1.017 3.026s-.893-.477-1.99-.477c-1.61 0-1.69 1.01-1.69 1.265 0 1.388 3.62 1.92 3.62 5.17 0 2.558-1.623 4.21-3.813 4.21-2.628 0-3.97-1.638-3.97-1.638l.702-2.32s1.383 1.187 2.55 1.187c.763 0 1.076-.6 1.076-1.04 0-1.813-2.973-1.895-2.973-4.872 0-2.507 1.8-4.934 5.433-4.934 1.4.002 2.072.423 2.072.423z"/>
      </svg>
    ),
  },
];

const IntegrationsCarousel = () => {
  const doubled = [...integrations, ...integrations];

  return (
    <section className="bg-[#080808] py-14 border-t border-white/5 overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 mb-8 text-center">
        <span className="text-[#E7E6E6]/20 text-[10px] font-mono tracking-[0.3em] uppercase">Platforms Raven connects to</span>
      </div>

      <div className="relative">
        <div className="absolute left-0 top-0 bottom-0 w-24 z-10 pointer-events-none"
          style={{background: 'linear-gradient(to right, #080808, transparent)'}} />
        <div className="absolute right-0 top-0 bottom-0 w-24 z-10 pointer-events-none"
          style={{background: 'linear-gradient(to left, #080808, transparent)'}} />
        <div className="flex gap-3 carousel-track-left" style={{width: 'max-content'}}>
          {doubled.map((item, i) => (
            <div key={i}
              className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg border border-white/5 bg-[#0F0F0E] whitespace-nowrap select-none flex-shrink-0">
              <span className="text-[#FB5005]/70">{item.icon}</span>
              <span className="font-body text-xs text-[#E7E6E6]/40 font-medium">{item.name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

// --- Problem ---
const Problem = () => (
  <section id="problem" className="bg-[#0A0A0A] py-32 border-t border-white/5 relative overflow-hidden">
    <div className="absolute right-0 top-0 w-[600px] h-[600px] bg-[#FB5005]/2 rounded-full blur-3xl pointer-events-none" />
    <div className="max-w-5xl mx-auto px-6 lg:px-8 relative">
      <div className="mb-14">
        <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">The problem</span>
        <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 leading-tight max-w-2xl">
          The work that eats your day.
        </h2>
      </div>

      <div className="grid lg:grid-cols-2 gap-16 items-start">
        <div className="space-y-6">
          <p className="text-[#E7E6E6]/60 font-body text-lg leading-relaxed">
            Your tools don&apos;t talk to each other. Your data lives in five places. Every project needs someone to check the status, move the card, send the update, find the file.
          </p>
          <p className="text-[#E7E6E6]/80 font-body text-lg leading-relaxed font-medium">
            That someone is you.
          </p>
          <p className="text-[#E7E6E6]/50 font-body text-base leading-relaxed">
            Until now you had two options: hire help you cannot afford, or keep doing it yourself and watch deep work disappear.
          </p>
          <div className="pt-4 border-t border-white/8">
            <p className="text-[#FB5005] font-heading font-semibold text-xl">
              There is a third option.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {[
            { label: 'Tools don\'t talk to each other', icon: '×' },
            { label: 'Data scattered across five platforms', icon: '×' },
            { label: 'You\'re the glue between every system', icon: '×' },
            { label: 'Deep work interrupted by status checks', icon: '×' },
            { label: 'Can\'t afford to hire, can\'t afford to keep doing it', icon: '×' },
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-4 bg-[#080808] border border-white/5 rounded">
              <span className="text-red-500/40 font-mono font-bold text-sm flex-shrink-0">{item.icon}</span>
              <span className="font-body text-[#E7E6E6]/40 text-sm">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  </section>
);

// --- Solution ---
const Solution = () => {
  const capabilities = [
    {
      icon: <Search size={20} className="text-[#FB5005]" />,
      title: 'Research & monitoring',
      desc: 'Scan sources, compile reports, flag changes. Check competitors. Track prices. Monitor dashboards.',
    },
    {
      icon: <Database size={20} className="text-[#FB5005]" />,
      title: 'Data movement',
      desc: 'Sync between Notion, Sheets, GitHub, your database. Update records. Fill templates.',
    },
    {
      icon: <RefreshCw size={20} className="text-[#FB5005]" />,
      title: 'Status & follow-up',
      desc: 'Check project status. Send updates to Slack. Remind stakeholders. Keep work moving.',
    },
    {
      icon: <Clock size={20} className="text-[#FB5005]" />,
      title: 'Scheduled tasks',
      desc: 'Run nightly. Run hourly. Trigger on events. Agents keep working when you are offline.',
    },
  ];

  return (
    <section id="solution" className="bg-[#080808] py-32 border-t border-white/5 relative overflow-hidden">
      <div className="absolute left-0 bottom-0 w-[500px] h-[500px] bg-[#FB5005]/2 rounded-full blur-3xl pointer-events-none" />
      <div className="max-w-7xl mx-auto px-6 lg:px-8 relative">
        <div className="grid lg:grid-cols-2 gap-20 items-start mb-20">
          <div>
            <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">The solution</span>
            <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 mb-8 leading-tight">
              Hire Raven, an agent<br />that never sleeps.
            </h2>
          </div>
          <div className="space-y-5 lg:pt-16">
            <p className="text-[#E7E6E6]/55 font-body text-base leading-relaxed">
              Raven is agent software that works autonomously. It checks your systems. It moves data between tools. It reports back when something needs your eyes. It runs overnight. It does not forget. It does not get bored.
            </p>
            <p className="text-[#E7E6E6]/55 font-body text-base leading-relaxed">
              ArcLink gives that agent a dedicated pod — secure infrastructure with memory, tools, and direct access to the apps you already use. Raven is your interface. You command from Telegram or Discord. The agent executes.
            </p>
          </div>
        </div>

        <div className="mb-8">
          <span className="text-[#E7E6E6]/30 text-xs font-mono tracking-widest uppercase">What agents handle</span>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-white/5 rounded-lg overflow-hidden">
          {capabilities.map((cap, i) => (
            <div key={i} className="bg-[#0F0F0E] p-8 group hover:bg-[#131312] transition-colors">
              <div className="w-10 h-10 bg-[#FB5005]/10 rounded-lg flex items-center justify-center mb-5 group-hover:bg-[#FB5005]/15 transition-colors">
                {cap.icon}
              </div>
              <h3 className="font-heading font-semibold text-[#E7E6E6] text-sm mb-3 leading-snug">{cap.title}</h3>
              <p className="font-body text-[#E7E6E6]/40 text-sm leading-relaxed">{cap.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

// --- Animated border SVG ---
const AnimatedBorderSVG = () => {
  const svgRef = useRef<SVGSVGElement>(null);
  const rectRef = useRef<SVGRectElement>(null);
  const dotRef = useRef<SVGCircleElement>(null);
  const glowRef = useRef<SVGCircleElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<number>(0);
  const progressRef = useRef(0);

  useEffect(() => {
    const container = containerRef.current;
    const svg = svgRef.current;
    const rect = rectRef.current;
    const dot = dotRef.current;
    const glow = glowRef.current;
    if (!container || !svg || !rect || !dot || !glow) return;

    const updateSize = () => {
      const { width, height } = container.getBoundingClientRect();
      svg.setAttribute('width', String(width));
      svg.setAttribute('height', String(height));
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      rect.setAttribute('width', String(width - 2));
      rect.setAttribute('height', String(height - 2));
    };

    const timer = setTimeout(() => {
      updateSize();
      window.addEventListener('resize', updateSize);

      const animate = () => {
        const totalLen = (rect as SVGGeometryElement).getTotalLength?.() ?? 0;
        if (totalLen === 0) { animRef.current = requestAnimationFrame(animate); return; }

        progressRef.current = (progressRef.current + totalLen / (60 * 20)) % totalLen;
        const pt = (rect as SVGGeometryElement).getPointAtLength(progressRef.current);

        dot.setAttribute('cx', String(pt.x + 1));
        dot.setAttribute('cy', String(pt.y + 1));
        glow.setAttribute('cx', String(pt.x + 1));
        glow.setAttribute('cy', String(pt.y + 1));

        animRef.current = requestAnimationFrame(animate);
      };
      animRef.current = requestAnimationFrame(animate);
    }, 100);

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(animRef.current);
      window.removeEventListener('resize', updateSize);
    };
  }, []);

  return (
    <div ref={containerRef} className="absolute inset-0 pointer-events-none" style={{zIndex: 10}}>
      <svg ref={svgRef} className="absolute inset-0" style={{overflow: 'visible'}}>
        <defs>
          <radialGradient id="dotGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FB5005" stopOpacity="1" />
            <stop offset="40%" stopColor="#FB5005" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#FB5005" stopOpacity="0" />
          </radialGradient>
          <filter id="glow-filter">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect
          x="1" y="1"
          rx="8" ry="8"
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth="1"
          ref={rectRef}
        />
        <circle ref={glowRef} r="10" fill="url(#dotGlow)" cx="-100" cy="-100" />
        <circle ref={dotRef} r="3.5" fill="#FB5005" cx="-100" cy="-100" filter="url(#glow-filter)" />
      </svg>
    </div>
  );
};

// --- How it works ---
const HowItWorks = () => {
  const steps = [
    {
      num: '01',
      title: 'Raven asks what you need.',
      body: 'Research? Data syncing? Reporting? Pick a starting point.',
      icon: <Bot size={20} className="text-[#FB5005]" />,
    },
    {
      num: '02',
      title: 'Name your agent.',
      body: 'Raven provisions a dedicated pod, wires the tools, arms the memory. Under 90 seconds.',
      icon: <Activity size={20} className="text-[#FB5005]" />,
    },
    {
      num: '03',
      title: 'Give instructions in plain language.',
      body: 'The agent executes. Raven reports back. You watch it work — or let it run and check later.',
      icon: <Zap size={20} className="text-[#FB5005]" />,
    },
  ];

  return (
    <section id="how-it-works" className="bg-[#0A0A0A] py-32 relative border-t border-white/5">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="mb-20">
          <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">How it works</span>
          <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 max-w-xl leading-tight">
            From idea to operating<br />in minutes.
          </h2>
        </div>

        <div className="relative">
          <AnimatedBorderSVG />
          <div className="grid md:grid-cols-3 gap-px bg-white/5 rounded-lg overflow-hidden">
            {steps.map((step, i) => (
              <div key={i} className="bg-[#0F0F0E] p-10 relative group hover:bg-[#131312] transition-colors">
                <span className="text-[#FB5005]/20 font-heading font-bold text-5xl mb-8 block select-none">{step.num}</span>
                <div className="flex items-center gap-3 mb-4">
                  {step.icon}
                  <h3 className="font-heading font-semibold text-[#E7E6E6] text-base">{step.title}</h3>
                </div>
                <p className="font-body text-[#E7E6E6]/50 text-sm leading-relaxed">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

// --- Comparison ---
const Comparison = () => {
  const rows = [
    { traditional: 'You manage tools', arclink: 'Raven runs systems' },
    { traditional: 'You follow up manually', arclink: 'Raven executes automatically' },
    { traditional: 'Work stops when you stop', arclink: 'Raven runs 24/7' },
    { traditional: 'You adapt to software', arclink: 'Raven adapts to you' },
    { traditional: 'Manual overhead', arclink: 'Zero overhead' },
    { traditional: 'Inconsistent output', arclink: 'System-driven consistency' },
    { traditional: 'Hire help you can\'t afford', arclink: 'Deploy agents from $149/mo' },
  ];

  return (
    <section className="bg-[#0F0F0E] py-32 border-t border-white/5">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-20">
          <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">The shift</span>
          <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 mb-4 leading-tight">
            Stop managing.<br />Let Raven run it.
          </h2>
        </div>

        <div className="max-w-2xl mx-auto">
          <div className="grid grid-cols-2 mb-2">
            <div className="text-[#E7E6E6]/20 text-xs font-mono tracking-widest uppercase px-6 pb-4">Traditional</div>
            <div className="text-[#FB5005] text-xs font-mono tracking-widest uppercase px-6 pb-4">With Raven</div>
          </div>
          <div className="rounded-lg overflow-hidden border border-white/5">
            {rows.map((row, i) => (
              <div key={i} className={`grid grid-cols-2 ${i !== rows.length - 1 ? 'border-b border-white/5' : ''}`}>
                <div className="px-6 py-4 text-[#E7E6E6]/30 font-body text-sm border-r border-white/5 flex items-center gap-3">
                  <span className="w-1.5 h-1.5 rounded-full bg-white/10 flex-shrink-0" />
                  {row.traditional}
                </div>
                <div className="px-6 py-4 bg-[#080808] text-[#E7E6E6]/80 font-body text-sm flex items-center gap-3">
                  <Check size={12} className="text-[#1AC153] flex-shrink-0" />
                  {row.arclink}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

// --- Pricing ---
const Pricing = () => {
  const plans = [
    {
      name: 'Founders',
      highlight: false,
      tag: 'Limited — 100 spots',
      price: '$149',
      sub: 'Sovereign equivalent',
      features: [
        'Single agent + ArcLink systems',
        'Raven command layer (Telegram & Discord)',
        'Core integrations (Notion, GitHub, webhooks, APIs)',
        'Basic memory & persistence',
        'Locked-in founder rate forever',
      ],
    },
    {
      name: 'Sovereign',
      highlight: false,
      tag: null,
      price: '$199',
      sub: 'per month',
      features: [
        'Single agent + ArcLink systems',
        'Raven command layer (Telegram & Discord)',
        'Core integrations (Notion, GitHub, webhooks, APIs)',
        'Full memory & persistence',
      ],
    },
    {
      name: 'Scale',
      highlight: true,
      tag: 'Most powerful',
      price: '$275',
      sub: 'per month',
      features: [
        'Three agents + ArcLink systems',
        'Federation Agent Deployment',
        'Agentic Federation: Shared Knowledge Vault',
        'Single Source of Truth + Swarm',
        'Priority provisioning & support',
      ],
    },
  ];

  return (
    <section id="pricing" className="bg-[#080808] py-32 border-t border-white/5 relative overflow-hidden">
      <div className="absolute left-1/2 top-1/3 -translate-x-1/2 w-[700px] h-[400px] bg-[#FB5005]/3 rounded-full blur-3xl pointer-events-none" />
      <div className="max-w-7xl mx-auto px-6 lg:px-8 relative">
        <div className="text-center mb-14">
          <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">Pricing</span>
          <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 mb-4 leading-tight">
            One agent. Clear price.
          </h2>
          <p className="text-[#E7E6E6]/30 font-body text-sm">No setup fees. No contracts. Cancel anytime.</p>
        </div>

        <div className="grid md:grid-cols-3 gap-px bg-white/5 rounded-lg overflow-hidden mb-10">
          {plans.map((plan, i) => (
            <div key={i}
              className={`p-10 relative flex flex-col transition-colors ${plan.highlight ? 'bg-[#131312]' : 'bg-[#0F0F0E] hover:bg-[#131312]'}`}>
              {plan.highlight && (
                <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-[#FB5005]/60 to-transparent" />
              )}
              {plan.tag && (
                <span className={`absolute top-4 right-4 text-[9px] font-mono tracking-widest uppercase px-2 py-0.5 rounded-full border ${
                  plan.highlight
                    ? 'text-[#FB5005] border-[#FB5005]/30'
                    : 'text-[#FB5005]/70 border-[#FB5005]/20'
                }`}>
                  {plan.tag}
                </span>
              )}
              <div className="mb-8">
                <h3 className="font-heading font-normal text-[#E7E6E6] text-lg mb-4">{plan.name}</h3>
                <div className="flex items-end gap-1 mb-1">
                  <span className="font-heading font-bold text-[#E7E6E6] text-4xl">{plan.price}</span>
                  <span className="text-[#E7E6E6]/30 font-body text-sm mb-1">/mo</span>
                </div>
                <p className="text-[#E7E6E6]/25 font-mono text-[10px] tracking-wide">{plan.sub}</p>
              </div>

              <ul className="space-y-3 flex-1 mb-8">
                {plan.features.map((f, j) => (
                  <li key={j} className="flex items-start gap-3 text-sm font-body text-[#E7E6E6]/60">
                    <Check size={13} className="text-[#1AC153] flex-shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>

              <Link href={`/onboarding?plan=${plan.name.toLowerCase()}`} className={`block w-full py-3 rounded font-body font-semibold text-sm text-center transition-all ${
                plan.highlight
                  ? 'bg-[#FB5005] hover:bg-[#e04504] text-white hover:shadow-[0_0_24px_rgba(251,80,5,0.35)]'
                  : plan.name === 'Founders'
                    ? 'bg-[#FB5005]/15 hover:bg-[#FB5005]/25 border border-[#FB5005]/30 text-[#FB5005] hover:text-[#FB5005]'
                    : 'bg-white/5 hover:bg-white/10 border border-white/10 text-[#E7E6E6]'
              }`}>
                {plan.name === 'Founders' ? 'Claim founder price' : 'Get started'}
              </Link>
            </div>
          ))}
        </div>

        {/* Agent Expansion */}
        <div className="rounded-lg border border-[#FB5005]/20 bg-[#FB5005]/5 px-7 py-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6 relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none"
            style={{backgroundImage: 'linear-gradient(90deg, rgba(251,80,5,0.04) 1px, transparent 1px)', backgroundSize: '32px 100%'}} />
          <div className="relative flex items-start sm:items-center gap-4">
            <div className="w-8 h-8 rounded bg-[#FB5005]/15 border border-[#FB5005]/30 flex items-center justify-center flex-shrink-0">
              <GitBranch size={15} className="text-[#FB5005]" />
            </div>
            <div>
              <span className="font-heading font-semibold text-[#E7E6E6] text-sm">Agent Expansion</span>
              <p className="text-[#E7E6E6]/45 font-body text-xs mt-0.5 leading-relaxed">
                Add agents to any plan &nbsp;·&nbsp; <span className="text-[#FB5005]">$99/mo per agent</span> on Sovereign &nbsp;·&nbsp; <span className="text-[#FB5005]">$79/mo per agent</span> on Scale
              </p>
            </div>
          </div>
          <a href="#cta" className="relative flex-shrink-0 bg-[#FB5005] hover:bg-[#e04504] text-white font-body font-semibold text-xs px-5 py-2.5 rounded transition-all hover:shadow-[0_0_20px_rgba(251,80,5,0.35)] whitespace-nowrap">
            Add an agent
          </a>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-6 pt-8">
          {[
            { icon: <Shield size={13} />, label: 'No setup fees' },
            { icon: <ArrowRight size={13} />, label: 'Cancel anytime' },
            { icon: <Zap size={13} />, label: 'Operational in minutes' },
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2 text-[#E7E6E6]/30 font-body text-xs">
              <span className="text-[#FB5005]/50">{item.icon}</span>
              {item.label}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

// --- Agent Questionnaire ---
const questions = [
  {
    id: 'time',
    q: 'Where does most of your time go each week?',
    options: [
      'Chasing updates & status checks',
      'Moving data between tools',
      'Following up with leads or clients',
      'Research and reporting',
    ],
  },
  {
    id: 'pain',
    q: 'What is your biggest operational headache?',
    options: [
      'Things fall through the cracks',
      'I\'m the only one who knows where everything lives',
      'I repeat the same tasks over and over',
      'I can\'t get to the important work',
    ],
  },
  {
    id: 'tools',
    q: 'Which tools do you use most?',
    options: [
      'Notion / Google Sheets',
      'GitHub / dev tools',
      'Slack / messaging',
      'CRM / sales tools',
    ],
  },
  {
    id: 'goal',
    q: 'What would a win look like for you?',
    options: [
      'Morning briefings without lifting a finger',
      'Data synced automatically, no manual entry',
      'Follow-ups sent before I remember to do them',
      'Reports compiled while I sleep',
    ],
  },
];

type Answers = Record<string, string>;

const recommendations: { match: (a: Answers) => boolean; plan: string; title: string; desc: string }[] = [
  {
    match: (a) => a.tools === 'GitHub / dev tools' || a.goal === 'Reports compiled while I sleep',
    plan: 'Scale',
    title: 'You need the Scale plan.',
    desc: 'You\'re running multi-step workflows across dev and data tools. Multiple agents and shared knowledge are the right fit.',
  },
  {
    match: (a) => a.time === 'Research and reporting' || a.goal === 'Morning briefings without lifting a finger',
    plan: 'Founders',
    title: 'Start with a research agent.',
    desc: 'Raven can scan your sources, compile what changed, and deliver a morning briefing. Founders gets one agent running fast.',
  },
  {
    match: (a) => a.time === 'Following up with leads or clients' || a.pain === 'Things fall through the cracks',
    plan: 'Founders',
    title: 'A follow-up agent is your first move.',
    desc: 'Raven handles outreach, reminders, and status pings automatically. Nothing slips. Founders is the right starting point.',
  },
  {
    match: () => true,
    plan: 'Founders',
    title: 'The Founders plan fits perfectly.',
    desc: 'You have clear repetitive tasks that should run themselves. Raven can be operational in minutes on Founders.',
  },
];

const AgentQuestionnaire = () => {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [done, setDone] = useState(false);

  const current = questions[step];
  const total = questions.length;

  const handleSelect = (option: string) => {
    const updated = { ...answers, [current.id]: option };
    setAnswers(updated);
    if (step < total - 1) {
      setTimeout(() => setStep(s => s + 1), 180);
    } else {
      setTimeout(() => setDone(true), 180);
    }
  };

  const result = recommendations.find(r => r.match(answers));

  const reset = () => {
    setStep(0);
    setAnswers({});
    setDone(false);
  };

  return (
    <section className="bg-[#0A0A0A] py-24 border-t border-white/5">
      <div className="max-w-2xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-12">
          <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">Not sure where to start?</span>
          <h2 className="font-heading font-normal text-[#E7E6E6] text-3xl lg:text-4xl mt-4 leading-tight">
            Find your first agent.
          </h2>
          <p className="text-[#E7E6E6]/40 font-body text-sm mt-3">
            Answer four quick questions. We&apos;ll point you in the right direction.
          </p>
        </div>

        <div className="bg-[#0F0F0E] border border-white/5 rounded-xl overflow-hidden">
          {!done ? (
            <div>
              {/* Progress bar */}
              <div className="h-px bg-white/5">
                <div
                  className="h-px bg-[#FB5005] transition-all duration-500"
                  style={{ width: `${((step) / total) * 100}%` }}
                />
              </div>

              <div className="p-8 lg:p-10">
                {/* Step counter */}
                <div className="flex items-center justify-between mb-8">
                  <span className="font-mono text-[10px] text-[#E7E6E6]/20 tracking-widest uppercase">
                    Question {step + 1} of {total}
                  </span>
                  <div className="flex gap-1.5">
                    {questions.map((_, i) => (
                      <div key={i} className={`w-1.5 h-1.5 rounded-full transition-colors ${i < step ? 'bg-[#FB5005]' : i === step ? 'bg-[#FB5005]/60' : 'bg-white/10'}`} />
                    ))}
                  </div>
                </div>

                <h3 className="font-heading font-medium text-[#E7E6E6] text-lg lg:text-xl mb-8 leading-snug">
                  {current.q}
                </h3>

                <div className="space-y-3">
                  {current.options.map((opt, i) => (
                    <button
                      key={i}
                      onClick={() => handleSelect(opt)}
                      className="w-full text-left px-5 py-4 rounded-lg border border-white/8 hover:border-[#FB5005]/40 hover:bg-[#FB5005]/5 text-[#E7E6E6]/60 hover:text-[#E7E6E6]/90 font-body text-sm transition-all group flex items-center gap-4"
                    >
                      <span className="w-5 h-5 rounded border border-white/10 group-hover:border-[#FB5005]/40 flex items-center justify-center flex-shrink-0 text-[#FB5005] text-[10px] font-mono transition-colors">
                        {String.fromCharCode(65 + i)}
                      </span>
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-8 lg:p-10">
              {/* Top accent line */}
              <div className="h-px bg-gradient-to-r from-transparent via-[#FB5005]/40 to-transparent mb-10" />

              <div className="flex items-start gap-4 mb-6">
                <div className="w-10 h-10 bg-[#FB5005]/10 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Zap size={18} className="text-[#FB5005]" />
                </div>
                <div>
                  <span className="font-mono text-[10px] text-[#FB5005]/60 tracking-widest uppercase">Recommendation</span>
                  <h3 className="font-heading font-semibold text-[#E7E6E6] text-xl mt-1">{result?.title}</h3>
                </div>
              </div>

              <p className="text-[#E7E6E6]/50 font-body text-sm leading-relaxed mb-8 pl-14">
                {result?.desc}
              </p>

              <div className="pl-14 flex flex-col sm:flex-row gap-3">
                <Link href="/onboarding?channel=telegram" className="flex items-center gap-3 bg-[#FB5005] hover:bg-[#e04504] text-white font-body font-semibold px-6 py-3 rounded transition-all hover:shadow-[0_0_24px_rgba(251,80,5,0.35)] text-sm justify-center">
                  <TelegramIcon /> Start with Telegram
                </Link>
                <button
                  onClick={reset}
                  className="px-6 py-3 rounded border border-white/10 hover:border-white/20 text-[#E7E6E6]/40 hover:text-[#E7E6E6]/60 font-body text-sm transition-all"
                >
                  Start over
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

// --- FAQ ---
const FAQ = () => {
  const [open, setOpen] = useState<number | null>(null);

  const faqs = [
    {
      q: 'What is an agent, exactly?',
      a: 'Software that works for you autonomously. You describe what you want — "check this dashboard every morning and message me if numbers drop" — and the agent executes. It runs on dedicated infrastructure, remembers context, and reports back.',
    },
    {
      q: 'Who is Raven?',
      a: 'Your ArcLink guide. Available in Telegram and Discord, Raven handles provisioning, teaches you commands, checks agent health, and helps you scale. No dashboard required.',
    },
    {
      q: 'Do I need to know how to code?',
      a: 'No. You give instructions in plain language. Raven translates. Technical users can go deeper. Everyone else points, clicks, and commands.',
    },
    {
      q: 'What if I do not know what to automate?',
      a: 'Start with status checks. "Tell me what changed in Notion today." Most users discover five more jobs within a week.',
    },
    {
      q: 'Is my data safe?',
      a: 'Yes. Agents run on isolated infrastructure. Your credentials stay encrypted. We do not train on your data. You control what the agent accesses.',
    },
  ];

  return (
    <section id="faq" className="bg-[#0A0A0A] py-32 border-t border-white/5">
      <div className="max-w-3xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-16">
          <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">FAQ</span>
          <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 leading-tight">
            Questions answered.
          </h2>
        </div>

        <div className="space-y-2">
          {faqs.map((faq, i) => (
            <div key={i} className="border border-white/5 rounded-lg overflow-hidden">
              <button
                onClick={() => setOpen(open === i ? null : i)}
                className="w-full flex items-center justify-between px-7 py-5 text-left hover:bg-white/3 transition-colors group"
              >
                <span className="font-heading font-medium text-[#E7E6E6]/80 text-sm group-hover:text-[#E7E6E6] transition-colors pr-6">
                  {faq.q}
                </span>
                <span className={`flex-shrink-0 w-5 h-5 flex items-center justify-center rounded border border-white/10 text-[#E7E6E6]/30 transition-all ${open === i ? 'border-[#FB5005]/30 text-[#FB5005]' : ''}`}>
                  {open === i ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </span>
              </button>
              <div className={`overflow-hidden transition-all duration-300 ${open === i ? 'max-h-60' : 'max-h-0'}`}>
                <p className="px-7 pb-6 font-body text-[#E7E6E6]/45 text-sm leading-relaxed">
                  {faq.a}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

// --- Platform Choice ---
const PlatformChoice = () => (
  <section className="bg-[#080808] py-32 border-t border-white/5">
    <div className="max-w-7xl mx-auto px-6 lg:px-8">
      <div className="text-center mb-20">
        <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">Platforms</span>
        <h2 className="font-heading font-normal text-[#E7E6E6] text-4xl lg:text-5xl mt-4 mb-4 leading-tight">
          Built where you already work.
        </h2>
        <p className="text-[#E7E6E6]/40 font-body text-sm">
          You don&apos;t learn a new platform. Raven runs where your conversations already happen.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-px bg-white/5 rounded-lg overflow-hidden max-w-3xl mx-auto">
        {[
          {
            icon: <TelegramIcon />,
            name: 'Telegram',
            color: '#2075FE',
            desc: 'Fast, direct, lightweight.',
            points: ['Instant message delivery', 'Personal & group workflows', 'Tell Raven, it executes'],
          },
          {
            icon: <DiscordIcon />,
            name: 'Discord',
            color: '#5865F2',
            desc: 'Structured, team-based workflows.',
            points: ['Channel-based operations', 'Role-based agent access', 'Team workflows, automated'],
          },
        ].map((p, i) => (
          <div key={i} className="bg-[#0F0F0E] p-10 group hover:bg-[#131312] transition-colors">
            <div className="w-12 h-12 rounded-lg flex items-center justify-center mb-6"
              style={{background: p.color + '15', border: `1px solid ${p.color}30`, color: p.color}}>
              {p.icon}
            </div>
            <h3 className="font-heading font-normal text-[#E7E6E6] text-2xl mb-2">{p.name}</h3>
            <p className="text-[#E7E6E6]/40 font-body text-sm mb-6">{p.desc}</p>
            <ul className="space-y-3">
              {p.points.map((pt, j) => (
                <li key={j} className="flex items-center gap-3 text-sm font-body text-[#E7E6E6]/60">
                  <Check size={13} style={{color: p.color, flexShrink: 0}} />
                  {pt}
                </li>
              ))}
            </ul>
            <Link href={`/onboarding?channel=${p.name.toLowerCase()}`} className="mt-8 block w-full py-3 rounded text-center font-body font-semibold text-sm transition-all"
              style={{background: p.color + '15', border: `1px solid ${p.color}30`, color: p.color}}
              onMouseEnter={e => (e.currentTarget.style.background = p.color + '25')}
              onMouseLeave={e => (e.currentTarget.style.background = p.color + '15')}>
              Start with {p.name}
            </Link>
          </div>
        ))}
      </div>
    </div>
  </section>
);

// --- Final CTA ---
const FinalCTA = () => (
  <section id="cta" className="bg-[#0F0F0E] py-32 border-t border-white/5 relative overflow-hidden">
    <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-[#FB5005]/5 rounded-full blur-3xl pointer-events-none" />
    <div className="relative max-w-4xl mx-auto px-6 lg:px-8 text-center">
      <span className="text-[#FB5005] text-xs font-mono tracking-widest uppercase">Get started</span>
      <h2 className="font-heading font-normal text-[#E7E6E6] leading-tight mb-4 mt-4"
        style={{fontSize: 'clamp(2.5rem, 6vw, 5rem)'}}>
        Reclaim your focus.
      </h2>
      <p className="text-[#E7E6E6]/45 font-body text-base mb-4 max-w-lg mx-auto leading-relaxed">
        Your first agent starts at $149/mo. Raven provisions it in minutes. Cancel anytime.
      </p>
      <p className="text-[#E7E6E6]/30 font-body text-sm mb-12">
        Join operators who stopped being the middleman for their own work.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
        <Link href="/onboarding?channel=telegram" className="flex items-center gap-3 bg-[#FB5005] hover:bg-[#e04504] text-white font-body font-semibold px-8 py-4 rounded transition-all hover:shadow-[0_0_48px_rgba(251,80,5,0.4)] w-full sm:w-auto justify-center">
          <TelegramIcon /> Start with Telegram
        </Link>
        <Link href="/onboarding?channel=discord" className="flex items-center gap-3 bg-transparent hover:bg-white/5 border border-white/15 hover:border-white/25 text-[#E7E6E6] font-body font-semibold px-8 py-4 rounded transition-all w-full sm:w-auto justify-center">
          <DiscordIcon /> Start with Discord
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-6">
        {[
          { icon: <Shield size={13} />, label: 'No setup fees' },
          { icon: <ArrowRight size={13} />, label: 'Cancel anytime' },
          { icon: <Zap size={13} />, label: 'Operational in minutes' },
          { icon: <Globe size={13} />, label: 'Runs 24/7' },
          { icon: <FileText size={13} />, label: 'From $149/mo' },
        ].map((item, i) => (
          <div key={i} className="flex items-center gap-2 text-[#E7E6E6]/25 font-body text-xs">
            <span className="text-[#FB5005]/40">{item.icon}</span>
            {item.label}
          </div>
        ))}
      </div>
    </div>
  </section>
);

export default function App() {
  return (
    <div className="bg-[#080808]" style={{fontFamily: 'Inter, sans-serif'}}>
      <Nav />
      <main>
        <Hero />
        <IntegrationsCarousel />
        <Problem />
        <Solution />
        <HowItWorks />
        <Comparison />
        <Pricing />
        <AgentQuestionnaire />
        <FAQ />
        <PlatformChoice />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
}
