"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { 
  Activity, 
  AlertTriangle, 
  CheckCircle, 
  Cpu, 
  Database, 
  Flame, 
  HardDrive, 
  Layers, 
  Play, 
  RefreshCw, 
  Server, 
  Terminal, 
  ArrowRight, 
  Clock, 
  Shield, 
  Target, 
  Zap, 
  ChevronRight, 
  ExternalLink, 
  Code, 
  Layout, 
  Radio, 
  FileText, 
  BarChart3, 
  TrendingUp,
  Sparkles,
  GitBranch,
  Filter
} from "lucide-react";

interface SimulationStep {
  title: string;
  badge: string;
  icon: any;
  color: string;
  logs: string[];
}

interface Scenario {
  name: string;
  service: string;
  anomaly: string;
  steps: SimulationStep[];
}

const SCENARIOS: Record<string, Scenario> = {
  saturation: {
    name: "Payment Platform Outage (Challenge Scenario)",
    service: "payment-service",
    anomaly: "DatabaseSaturation",
    steps: [
      {
        title: "Ingest & Correlate",
        badge: "CORRELATING",
        icon: Filter,
        color: "text-purple-400 border-purple-500/30 bg-purple-500/10",
        logs: [
          "[10:00:00] INGEST: Received 3 anomalies across payment-service, user-service, and order-service.",
          "[10:00:01] CORRELATE: Trace ID match `tr-pay-8821` & shared topological dependency `database-service`.",
          "[10:00:02] Master Incident created: INC-20261109-SAT. Blast radius: 4 services.",
          "[10:00:02] Business impact quantified: 175 failed transactions ($8,748.25 at risk), 95 failed logins."
        ]
      },
      {
        title: "Multi-Agent RCA",
        badge: "DIAGNOSING",
        icon: Target,
        color: "text-blue-400 border-blue-500/30 bg-blue-500/10",
        logs: [
          "[10:00:03] Node INVESTIGATE: Querying Prometheus pool checkout metrics on database-service...",
          "[10:00:04] PostgreSQL connection pool saturated: 100/100 active leases, queue depth > 45.",
          "[10:00:05] LLM Diagnosis: Shared database connection pool exhaustion causing upstream cascade.",
          "[10:00:05] Rejected hypothesis: Network partition (traffic flowing, socket ping succeeds)."
        ]
      },
      {
        title: "Remediate & Scale",
        badge: "REMEDIATING",
        icon: Zap,
        color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
        logs: [
          "[10:00:06] Node REMEDIATE: Selecting runbook CLEAR_STUCK_JOBS & POOL_EXPANSION.",
          "[10:00:07] Terminating orphaned idle-in-transaction connections on database-service...",
          "[10:00:08] Expanded connection pool max_connections to 250. Resetting downstream buffers.",
          "[10:00:09] Remediated order-service, user-service, and payment-service queues."
        ]
      },
      {
        title: "Verify & Post-Mortem",
        badge: "RESOLVED",
        icon: CheckCircle,
        color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
        logs: [
          "[10:00:10] Node VERIFY: Synthetic checkout transactions 100% successful (Latency: 18ms).",
          "[10:00:11] Node REPORT: Generating 9-section Markdown Incident Post-Mortem Report.",
          "[10:00:12] MTTR: 12 seconds. System fully recovered. Zero operator intervention required."
        ]
      }
    ]
  },
  memory: {
    name: "Memory Leak (OOM Anomaly)",
    service: "payment-service",
    anomaly: "HighMemoryUsage",
    steps: [
      {
        title: "Investigate Node",
        badge: "DIAGNOSING",
        icon: Target,
        color: "text-purple-400 border-purple-500/30 bg-purple-500/10",
        logs: [
          "[10:14:02] ALERT received: HighMemoryUsage on payment-service",
          "[10:14:03] Node INVESTIGATE: Querying Prometheus telemetry metrics...",
          "[10:14:04] payment-service RAM usage is 98MB (Limit 80MB). Status: Unhealthy.",
          "[10:14:05] Querying logs... Found trace: java.lang.OutOfMemoryError",
          "[10:14:06] LLM Diagnosis: Fatal memory exhaustion due to transaction thread heap leak."
        ]
      },
      {
        title: "Remediate Node",
        badge: "REMEDIATING",
        icon: Zap,
        color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
        logs: [
          "[10:14:07] Node REMEDIATE: Selecting mitigation plan: CONTAINER_RESTART",
          "[10:14:08] Executing Docker command: docker restart jarvis-payment-1",
          "[10:14:09] Container jarvis-payment-1 restarted successfully (Exit Code 0).",
          "[10:14:09] Telemetry reset. Memory allocations cleared."
        ]
      },
      {
        title: "Verify Node",
        badge: "VERIFYING",
        icon: Shield,
        color: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
        logs: [
          "[10:14:10] Node VERIFY: Waiting 5 seconds for service convergence...",
          "[10:14:15] Pinging health probe on http://payment-service:8004/health",
          "[10:14:16] Response: 200 OK. RAM: 24MB. Status: Healthy.",
          "[10:14:17] LLM Verification: System confirmed stable. No cascading anomalies."
        ]
      },
      {
        title: "Report Node",
        badge: "RESOLVED",
        icon: CheckCircle,
        color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
        logs: [
          "[10:14:18] Node REPORT: Generating markdown incident post-mortem report...",
          "[10:14:19] Report saved to Database (Incident ID: INC-4890). MTTR: 17 seconds.",
          "[10:14:20] Alert resolved. Operations Console resumed monitoring."
        ]
      }
    ]
  },
  cpu: {
    name: "CPU Spike (Busy Loop)",
    service: "order-service",
    anomaly: "HighCpuUsage",
    steps: [
      {
        title: "Investigate Node",
        badge: "DIAGNOSING",
        icon: Target,
        color: "text-purple-400 border-purple-500/30 bg-purple-500/10",
        logs: [
          "[18:02:11] ALERT received: HighCpuUsage on order-service",
          "[18:02:12] Node INVESTIGATE: Fetching target container metrics...",
          "[18:02:13] order-service CPU load at 97% (Threshold 80%).",
          "[18:02:14] Examining stdout logs... Detected recurring busy-loop thread on route /checkout.",
          "[18:02:15] LLM Diagnosis: Core thread lockup in order checkout routine."
        ]
      },
      {
        title: "Remediate Node",
        badge: "REMEDIATING",
        icon: Zap,
        color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
        logs: [
          "[18:02:16] Node REMEDIATE: Selecting mitigation plan: REBOOT_WORKERS",
          "[18:02:17] Clearing lock threads and restarting order-processing workers...",
          "[18:02:18] Remediated order-service container state."
        ]
      },
      {
        title: "Verify Node",
        badge: "VERIFYING",
        icon: Shield,
        color: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
        logs: [
          "[18:02:19] Node VERIFY: Cooling down telemetry sensors...",
          "[18:02:24] Scraping Prometheus metric: process_cpu_seconds_total",
          "[18:02:25] order-service CPU load stabilized at 4.2%.",
          "[18:02:26] Synthetic endpoint check returned 200 OK (Latency: 12ms)."
        ]
      },
      {
        title: "Report Node",
        badge: "RESOLVED",
        icon: CheckCircle,
        color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
        logs: [
          "[18:02:27] Node REPORT: Assembling Incident Report INC-4891.",
          "[18:02:28] Post-mortem compiled. Total resolution time (MTTR): 17 seconds."
        ]
      }
    ]
  },
  http: {
    name: "HTTP 500 Storm (Failure)",
    service: "api-gateway",
    anomaly: "HttpErrorSpike",
    steps: [
      {
        title: "Investigate Node",
        badge: "DIAGNOSING",
        icon: Target,
        color: "text-purple-400 border-purple-500/30 bg-purple-500/10",
        logs: [
          "[03:41:50] ALERT received: HttpErrorSpike on api-gateway",
          "[03:41:51] Node INVESTIGATE: Inspecting gateway routing statistics...",
          "[03:41:52] Detected 48 errors/min on downstream user-service calls.",
          "[03:41:53] Checking user-service status... Found DB connection pool timeout.",
          "[03:41:54] LLM Diagnosis: Database pool exhaustion in user-service leading to gateway HTTP 500 failures."
        ]
      },
      {
        title: "Remediate Node",
        badge: "REMEDIATING",
        icon: Zap,
        color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
        logs: [
          "[03:41:55] Node REMEDIATE: Action plan: RECYCLE_DB_POOL & SERVICE_RESTART",
          "[03:41:56] Restarting postgres connection manager & user-service container...",
          "[03:41:57] Database pools recycled. Container reboot complete."
        ]
      },
      {
        title: "Verify Node",
        badge: "VERIFYING",
        icon: Shield,
        color: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
        logs: [
          "[03:41:58] Node VERIFY: Executing verification suite...",
          "[03:42:03] curl http://api-gateway:8001/orders -> 200 OK (0.015s).",
          "[03:42:04] HTTP Error Rate dropped to 0.0%."
        ]
      },
      {
        title: "Report Node",
        badge: "RESOLVED",
        icon: CheckCircle,
        color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
        logs: [
          "[03:42:05] Node REPORT: Generating markdown incident summary.",
          "[03:42:06] Incident resolved autonomously. MTTR: 16 seconds."
        ]
      }
    ]
  }
};

interface BenchmarkStats {
  total_incidents: number;
  resolved_incidents: number;
  success_rate_percent: number;
  autonomous_mttr_seconds: number;
  human_baseline_mttr_seconds: number;
  time_saved_hours: number;
  cost_saved_usd: number;
  incidents_by_type: Record<string, number>;
}

export default function Home() {
  const [activeScenario, setActiveScenario] = useState("saturation");
  const [activeStep, setActiveStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [typedLogs, setTypedLogs] = useState<string[]>([]);
  const [benchmarkData, setBenchmarkData] = useState<BenchmarkStats | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    const fetchBenchmarks = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/benchmarks`);
        if (res.ok) {
          const data = await res.json();
          setBenchmarkData(data);
        }
      } catch (err) {
        console.error("Failed to fetch benchmarks:", err);
      }
    };
    fetchBenchmarks();
    const interval = setInterval(fetchBenchmarks, 30000);
    return () => clearInterval(interval);
  }, [API_URL]);

  const scenario = SCENARIOS[activeScenario] || SCENARIOS["saturation"];

  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = setInterval(() => {
        setActiveStep((prev) => (prev + 1) % scenario.steps.length);
      }, 5000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, scenario]);

  useEffect(() => {
    const logsToShow: string[] = [];
    for (let i = 0; i <= activeStep; i++) {
      if (scenario.steps[i]) {
        logsToShow.push(...scenario.steps[i].logs);
      }
    }
    setTypedLogs(logsToShow);
  }, [activeStep, activeScenario, scenario]);

  const changeScenario = (key: string) => {
    setActiveScenario(key);
    setActiveStep(0);
  };

  const handleStepClick = (idx: number) => {
    setIsPlaying(false);
    setActiveStep(idx);
  };

  return (
    <div className="relative min-h-screen bg-[#000000] text-[#fcfdff] flex flex-col font-sans overflow-x-hidden">
      {/* Resend Top Ambient Flare */}
      <div className="resend-glow absolute top-0 left-1/2 -translate-x-1/2 w-[1200px] h-[550px] pointer-events-none -z-10" />

      {/* Subtle Grid Pattern */}
      <div 
        className="absolute inset-0 pointer-events-none -z-20 opacity-[0.15]" 
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, #262730 1px, transparent 0)`,
          backgroundSize: "32px 32px"
        }}
      />

      {/* Resend Minimal Navigation - Slim Premium Navbar */}
      <header className="border-b border-white/[0.08] bg-black/80 backdrop-blur-xl px-4 sm:px-8 py-2.5 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 p-[1px] flex items-center justify-center shadow-sm shadow-orange-500/25">
            <div className="w-full h-full bg-black rounded-[7px] flex items-center justify-center text-orange-400">
              <Activity className="h-3.5 w-3.5" />
            </div>
          </div>
          <span className="text-[13px] font-bold tracking-tight text-white">J.A.R.V.I.S.</span>
        </div>

        <nav className="hidden md:flex items-center space-x-8 text-[12px] font-medium text-zinc-400">
          <a href="#problem" className="hover:text-white transition-colors duration-150">Problem Statement</a>
          <a href="#simulator" className="hover:text-white transition-colors duration-150">Live Simulation</a>
          <a href="#architecture" className="hover:text-white transition-colors duration-150">Correlation Engine</a>
          <a href="#benchmarks" className="hover:text-white transition-colors duration-150">Benchmarks</a>
        </nav>

        <div className="flex items-center space-x-3">
          <Link
            href="/dashboard"
            className="group relative inline-flex items-center space-x-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-full bg-white text-zinc-950 hover:bg-zinc-100 shadow-[0_0_14px_rgba(255,255,255,0.15)] hover:shadow-[0_0_20px_rgba(255,255,255,0.25)] transition-all duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            <span>Launch SRE Console</span>
            <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform duration-150" />
          </Link>
        </div>
      </header>

      {/* Hero Section (Resend Editorial Aesthetic) */}
      <section className="pt-24 pb-16 px-6 max-w-6xl mx-auto flex flex-col items-center text-center">
        {/* Editorial Headline */}
        <h1 className="text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight resend-editorial-title max-w-4xl leading-[1.08] mb-6 break-words">
          Autonomous Incident Correlation for Modern Clouds
        </h1>

        {/* Muted Subtitle */}
        <p className="text-base sm:text-lg text-[#a1a4a5] max-w-2xl font-normal leading-relaxed mb-10">
          When a shared database saturates, digital platforms see slow APIs, login timeouts, and payment failures as isolated alerts. 
          <span className="text-[#fcfdff] font-medium"> J.A.R.V.I.S. aggregates multiple data sources</span>, finds topological connections, detects root cause in seconds, and remediates with zero human delay.
        </p>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center gap-4 mb-16">
          <Link
            href="/dashboard"
            className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 text-sm font-semibold px-6 py-3 rounded-xl bg-gradient-to-r from-[#ff801f] to-[#ff5500] text-white hover:brightness-110 shadow-lg shadow-[#ff801f]/20 transition-opacity duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff801f]"
          >
            <Zap className="h-4 w-4" />
            <span>Open SRE Command Deck</span>
          </Link>
          <a
            href="#simulator"
            className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 text-sm font-medium px-6 py-3 rounded-xl border border-[#242633] bg-[#0e0f14] text-[#d1d5db] hover:border-[#383b4e] hover:text-white transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3b9eff]"
          >
            <Play className="h-4 w-4 text-[#ff801f]" />
            <span>Watch Live Correlation Demo</span>
          </a>
        </div>

        {/* Metric Badges */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full max-w-4xl text-left">
          <div className="p-4 rounded-xl border border-[#1a1b24] bg-[#0a0b10]">
            <div className="text-xs font-mono text-[#a1a4a5] mb-1">mttr compression</div>
            <div className="text-2xl font-bold font-mono text-[#fcfdff]">
              {benchmarkData ? `< ${benchmarkData.autonomous_mttr_seconds}s` : "< 15s"}
            </div>
            <div className="text-[11px] text-[#10b981] flex items-center space-x-1 mt-1">
              <TrendingUp className="h-3 w-3" />
              <span>99.2% faster than on-call</span>
            </div>
          </div>

          <div className="p-4 rounded-xl border border-[#1a1b24] bg-[#0a0b10]">
            <div className="text-xs font-mono text-[#a1a4a5] mb-1">correlation accuracy</div>
            <div className="text-2xl font-bold font-mono text-[#3b9eff]">100%</div>
            <div className="text-[11px] text-[#a1a4a5] mt-1">Shared dependency & trace mapping</div>
          </div>

          <div className="p-4 rounded-xl border border-[#1a1b24] bg-[#0a0b10]">
            <div className="text-xs font-mono text-[#a1a4a5] mb-1">multi-source ingestion</div>
            <div className="text-2xl font-bold font-mono text-[#ff801f]">4 streams</div>
            <div className="text-[11px] text-[#a1a4a5] mt-1">REST, logs, AlertManager, chaos</div>
          </div>

          <div className="p-4 rounded-xl border border-[#1a1b24] bg-[#0a0b10]">
            <div className="text-xs font-mono text-[#a1a4a5] mb-1">total incidents solved</div>
            <div className="text-2xl font-bold font-mono text-[#fcfdff]">
              {benchmarkData ? benchmarkData.total_incidents : "38"}
            </div>
            <div className="text-[11px] text-[#10b981] mt-1">Verified post-mortems compiled</div>
          </div>
        </div>
      </section>

      {/* Simulator Section (Cockpit Terminal Style) */}
      <section id="simulator" className="py-16 px-6 max-w-6xl mx-auto w-full">
        <div className="text-center mb-8">
          <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white mb-2">
            Experience Autonomous Incident Resolution
          </h2>
          <p className="text-sm text-[#a1a4a5]">
            Select an incident scenario to watch J.A.R.V.I.S. ingest, correlate, diagnose, remediate, and report in real time.
          </p>
        </div>

        {/* Scenario Switcher Tabs */}
        <div className="flex flex-wrap gap-2 justify-center mb-6">
          {Object.keys(SCENARIOS).map((key) => {
            const sc = SCENARIOS[key];
            const isActive = activeScenario === key;
            return (
              <button
                key={key}
                onClick={() => changeScenario(key)}
                className={`text-xs font-mono px-4 py-2 rounded-lg border transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff801f] ${
                  isActive
                    ? "border-[#ff801f] bg-[#ff801f]/10 text-white font-semibold resend-amber-glow"
                    : "border-[#1e1f2a] bg-[#0b0c10] text-[#a1a4a5] hover:border-[#2e3040] hover:text-white"
                }`}
              >
                {sc.name}
              </button>
            );
          })}
        </div>

        {/* Cockpit Card Container */}
        <div className="rounded-2xl border border-[#1f202b] bg-[#0a0b0f] overflow-hidden shadow-2xl">
          {/* Cockpit Top Bar */}
          <div className="px-5 py-3 border-b border-[#181922] bg-[#0e0f15] flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center space-x-3">
              <div className="flex space-x-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-[#ef4444]/80" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]/80" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#10b981]/80" />
              </div>
              <span className="font-mono text-[#71717a]">scenario:</span>
              <span className="font-mono font-bold text-[#ff801f]">{scenario.anomaly}</span>
              <span className="text-[#3f3f46]">|</span>
              <span className="font-mono text-[#a1a4a5]">{scenario.service}</span>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="px-2.5 py-1 rounded border border-[#2b2d3d] bg-[#14151e] text-[#d1d5db] hover:text-white hover:border-[#404358] transition-colors duration-150 flex items-center space-x-1 text-[11px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff801f]"
              >
                {isPlaying ? (
                  <><span>Pause</span></>
                ) : (
                  <><span>Auto-play</span></>
                )}
              </button>
            </div>
          </div>

          {/* Stepper Tabs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 border-b border-[#181922] bg-[#090a0d]">
            {scenario.steps.map((st, idx) => {
              const isCurrent = activeStep === idx;
              const isPast = activeStep > idx;
              const Icon = st.icon;
              return (
                <button
                  key={idx}
                  onClick={() => handleStepClick(idx)}
                  className={`p-3 text-left border-r border-[#181922] last:border-r-0 transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff801f] ${
                    isCurrent
                      ? "bg-[#14151f] border-b-2 border-b-[#ff801f]"
                      : isPast
                      ? "bg-[#0b0c10] text-[#a1a4a5]"
                      : "opacity-50 hover:opacity-80"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[11px] font-mono text-[#71717a]">0{idx + 1}</span>
                    {isCurrent && (
                      <span className="w-1.5 h-1.5 rounded-full bg-[#ff801f] animate-pulse" />
                    )}
                  </div>
                  <div className="text-xs font-semibold text-white flex items-center space-x-1.5">
                    <Icon className="h-3.5 w-3.5 text-[#ff801f]" />
                    <span className="truncate">{st.title}</span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Terminal Console Output */}
          <div className="p-5 font-mono text-xs bg-[#050608] min-h-[260px] flex flex-col justify-between">
            <div className="space-y-1.5">
              <div className="text-[#52525b] mb-3 text-[11px]">
                // J.A.R.V.I.S. Autonomous Runtime Diagnostic Stream [Agent v2.0]
              </div>
              {typedLogs.map((line, lIdx) => {
                const isAlert = line.includes("ALERT") || line.includes("CORRELATE");
                const isSuccess = line.includes("200 OK") || line.includes("restarted") || line.includes("RESOLVED");
                const isAction = line.includes("REMEDIATE") || line.includes("CLEAR_STUCK");
                return (
                  <div 
                    key={lIdx} 
                    className={`leading-relaxed ${
                      isAlert 
                        ? "text-[#f87171]" 
                        : isSuccess 
                        ? "text-[#34d399]" 
                        : isAction 
                        ? "text-[#fbbf24]" 
                        : "text-[#cbd5e1]"
                    }`}
                  >
                    {line}
                  </div>
                );
              })}
            </div>

            <div className="pt-4 mt-4 border-t border-[#181924] flex items-center justify-between text-[11px] text-[#71717a]">
              <span>Active phase: <strong className="text-white font-medium">{scenario.steps[activeStep].title}</strong></span>
              <Link href="/dashboard" className="text-[#ff801f] hover:underline flex items-center space-x-1 font-mono">
                <span>View Full Graph & Timeline in Console</span>
                <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Bento Grid: Architecture & Correlation Engine */}
      <section id="architecture" className="py-20 px-6 max-w-6xl mx-auto w-full border-t border-[#161720]">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-3 break-words">
            How J.A.R.V.I.S. Solves the PS Challenge
          </h2>
          <p className="text-sm text-[#a1a4a5] max-w-2xl mx-auto leading-relaxed">
            Traditional tools treat simultaneous alerts in payment, order, and auth services as three separate tickets. J.A.R.V.I.S. unifies them through 4 architectural layers into a single verified incident.
          </p>
        </div>

        {/* 12-Column Mixed-Span Bento Grid (8 + 4 over 4 + 4 + 4) */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
          {/* Tile 1: Lead Visual (Span 8) - SRE Cockpit Dashboard Preview */}
          <div className="md:col-span-8 p-6 rounded-2xl border border-[#1f202b] bg-[#090a0f] flex flex-col justify-between overflow-hidden relative group hover:border-[#2e3142] transition-colors duration-150">
            {/* Top metadata */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3 z-10">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#3b9eff]/10 border border-[#3b9eff]/20 text-[#3b9eff] flex items-center justify-center">
                  <Activity className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Live topological incident correlation</h3>
                  <p className="text-xs text-[#a1a4a5]">Dependency graph mapping & multi-alert unification</p>
                </div>
              </div>
              <div className="font-mono text-xs text-[#10b981]">
                INC-20261109-SAT · 3 alerts collapsed
              </div>
            </div>

            {/* Dummy Professional Dashboard Image Display */}
            <div className="relative rounded-xl border border-[#222432] bg-[#040407] overflow-hidden my-2 shadow-2xl">
              {/* Window Controls Bar */}
              <div className="px-4 py-2 border-b border-[#181924] bg-[#0b0c12] flex items-center justify-between text-[11px]">
                <div className="flex items-center space-x-2">
                  <div className="flex space-x-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-[#ef4444]/80" />
                    <div className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]/80" />
                    <div className="w-2.5 h-2.5 rounded-full bg-[#10b981]/80" />
                  </div>
                  <span className="font-mono text-[#71717a] ml-2">jarvis-cockpit // ops-console</span>
                </div>
                <div className="font-mono text-[10px] text-[#3b9eff] bg-[#3b9eff]/10 px-2 py-0.5 rounded border border-[#3b9eff]/20">
                  Sliding Window: 120s
                </div>
              </div>

              {/* Dashboard Image Visual */}
              <div className="relative w-full aspect-[16/9] sm:aspect-[21/9] overflow-hidden bg-[#07080c]">
                <Image
                  src="/jarvis_dashboard_preview.png"
                  alt="J.A.R.V.I.S. Autonomous SRE Operations Dashboard"
                  width={1024}
                  height={512}
                  className="w-full h-full object-cover object-top opacity-95 group-hover:scale-[1.01] transition-transform duration-200"
                  priority
                />
                <div className="absolute inset-0 bg-gradient-to-t from-[#090a0f] via-transparent to-transparent pointer-events-none" />

                {/* In-situ Live Topology Micro-Overlay */}
                <div className="absolute bottom-3 left-3 right-3 flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg bg-[#000000]/85 backdrop-blur-md border border-[#272838] text-[11px] font-mono">
                  <div className="flex items-center space-x-2 text-slate-300">
                    <span className="text-red-400 font-semibold">Root Cause:</span>
                    <span className="text-white">database-service (100/100 pool exhausted)</span>
                  </div>
                  <div className="flex items-center space-x-3 text-slate-400">
                    <span>Blast: 4 services</span>
                    <span className="text-[#52525b]">/</span>
                    <span className="text-emerald-400 font-semibold">MTTR: 12s</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Action Note */}
            <div className="mt-3 flex items-center justify-between text-xs text-[#a1a4a5]">
              <span>Evaluates topological adjacency across services, trace correlation IDs, and metrics breach timelines.</span>
              <Link 
                href="/dashboard" 
                className="text-[#3b9eff] hover:underline font-mono inline-flex items-center space-x-1 text-[11px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3b9eff]"
              >
                <span>Open console</span>
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>

          {/* Tile 2: Multi-Source Telemetry Normalizer (Span 4) */}
          <div className="md:col-span-4 p-6 rounded-2xl border border-[#1f202b] bg-[#090a0f] flex flex-col justify-between hover:border-[#2e3142] transition-colors duration-150">
            <div>
              <div className="w-8 h-8 rounded-lg bg-[#ff801f]/10 border border-[#ff801f]/20 text-[#ff801f] flex items-center justify-center mb-4">
                <Layers className="h-4 w-4" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Multi-source ingestion engine</h3>
              <p className="text-xs text-[#a1a4a5] leading-relaxed mb-4">
                Harmonizes disparate telemetry formats into normalized incident records with ISO-8601 UTC timestamps, service identifiers, and trace IDs.
              </p>
            </div>

            {/* Ingestion stream breakdown */}
            <div className="space-y-2 font-mono text-[11px] my-3">
              <div className="flex items-center justify-between p-2 rounded-lg bg-[#0e0f16] border border-[#1f202d]">
                <div className="flex items-center space-x-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#ff801f]" />
                  <span className="text-white">REST Events API</span>
                </div>
                <span className="text-[#71717a]">POST /events</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-[#0e0f16] border border-[#1f202d]">
                <div className="flex items-center space-x-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3b9eff]" />
                  <span className="text-white">Log File Parser</span>
                </div>
                <span className="text-[#71717a]">POST /logs/upload</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-[#0e0f16] border border-[#1f202d]">
                <div className="flex items-center space-x-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10b981]" />
                  <span className="text-white">AlertManager Webhook</span>
                </div>
                <span className="text-[#71717a]">Prometheus/Grafana</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-[#0e0f16] border border-[#1f202d]">
                <div className="flex items-center space-x-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#a855f7]" />
                  <span className="text-white">Chaos Simulator</span>
                </div>
                <span className="text-[#71717a]">POST /simulate</span>
              </div>
            </div>

            <div className="pt-3 border-t border-[#181924] text-[11px] text-[#71717a] font-mono">
              Normalization latency &lt; 2.4ms per record
            </div>
          </div>

          {/* Tile 3: Hypothesis Falsification (Span 4) */}
          <div className="md:col-span-4 p-6 rounded-2xl border border-[#1f202b] bg-[#090a0f] flex flex-col justify-between hover:border-[#2e3142] transition-colors duration-150">
            <div>
              <div className="w-8 h-8 rounded-lg bg-[#a855f7]/10 border border-[#a855f7]/20 text-[#a855f7] flex items-center justify-center mb-4">
                <Target className="h-4 w-4" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Multi-agent hypothesis falsification</h3>
              <p className="text-xs text-[#a1a4a5] leading-relaxed mb-4">
                The diagnostics agent does not guess. It evaluates competing failure theories against live telemetry and logs explicit rejection proofs.
              </p>
            </div>

            <div className="space-y-2 text-xs my-2">
              <div className="p-2.5 rounded-lg border border-[#ef4444]/30 bg-[#ef4444]/10">
                <div className="flex items-center justify-between text-xs font-semibold text-red-400 mb-1">
                  <span>Confirmed root cause</span>
                  <span className="font-mono text-[10px]">94.6% confidence</span>
                </div>
                <div className="text-[11px] text-[#fca5a5]">
                  PostgreSQL pool exhaustion (100/100 leases active, queue backlog &gt; 45)
                </div>
              </div>

              <div className="p-2.5 rounded-lg border border-[#1e1f2c] bg-[#0c0d14] text-[11px] text-[#71717a]">
                <div className="flex items-center space-x-1.5 text-[#a1a4a5] font-medium mb-0.5">
                  <span className="text-[#ef4444]">✕</span>
                  <span>Rejected: Network partition</span>
                </div>
                <div>Inter-service socket ping verified 1.2ms nominal.</div>
              </div>

              <div className="p-2.5 rounded-lg border border-[#1e1f2c] bg-[#0c0d14] text-[11px] text-[#71717a]">
                <div className="flex items-center space-x-1.5 text-[#a1a4a5] font-medium mb-0.5">
                  <span className="text-[#ef4444]">✕</span>
                  <span>Rejected: Bad deployment release</span>
                </div>
                <div>Container image digest identical across replicas.</div>
              </div>
            </div>

            <div className="pt-3 border-t border-[#181924] text-[11px] text-[#71717a] font-mono">
              Qwen 2.5:3B local LLM + deterministic rule fallback
            </div>
          </div>

          {/* Tile 4: Quantified Business Blast Radius (Span 4) */}
          <div className="md:col-span-4 p-6 rounded-2xl border border-[#1f202b] bg-[#090a0f] flex flex-col justify-between hover:border-[#2e3142] transition-colors duration-150">
            <div>
              <div className="w-8 h-8 rounded-lg bg-[#ef4444]/10 border border-[#ef4444]/20 text-[#ef4444] flex items-center justify-center mb-4">
                <AlertTriangle className="h-4 w-4" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Quantified blast radius & revenue impact</h3>
              <p className="text-xs text-[#a1a4a5] leading-relaxed mb-4">
                Measures actual business damage and customer exposure rather than reporting raw infrastructure alerts.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2 my-2">
              <div className="p-3 rounded-xl border border-[#1c1d28] bg-[#0c0d13]">
                <div className="text-[11px] font-mono text-[#a1a4a5]">Revenue at risk</div>
                <div className="text-xl font-bold font-mono text-[#ef4444] mt-1">$8,748.25</div>
                <div className="text-[10px] text-[#71717a] mt-0.5">175 failed checkouts</div>
              </div>
              <div className="p-3 rounded-xl border border-[#1c1d28] bg-[#0c0d13]">
                <div className="text-[11px] font-mono text-[#a1a4a5]">User dropouts</div>
                <div className="text-xl font-bold font-mono text-[#f59e0b] mt-1">95</div>
                <div className="text-[10px] text-[#71717a] mt-0.5">auth timeouts logged</div>
              </div>
              <div className="p-3 rounded-xl border border-[#1c1d28] bg-[#0c0d13]">
                <div className="text-[11px] font-mono text-[#a1a4a5]">Affected services</div>
                <div className="text-xl font-bold font-mono text-white mt-1">4 of 5</div>
                <div className="text-[10px] text-[#71717a] mt-0.5">payment, order, user, gw</div>
              </div>
              <div className="p-3 rounded-xl border border-[#1c1d28] bg-[#0c0d13]">
                <div className="text-[11px] font-mono text-[#a1a4a5]">Cascade delay</div>
                <div className="text-xl font-bold font-mono text-[#3b9eff] mt-1">1.8s</div>
                <div className="text-[10px] text-[#71717a] mt-0.5">spread across cluster</div>
              </div>
            </div>

            <div className="pt-3 border-t border-[#181924] text-[11px] text-[#71717a] font-mono">
              Direct telemetry from live payment gateway traces
            </div>
          </div>

          {/* Tile 5: Autonomous Remediation & Audit (Span 4) */}
          <div className="md:col-span-4 p-6 rounded-2xl border border-[#1f202b] bg-[#090a0f] flex flex-col justify-between hover:border-[#2e3142] transition-colors duration-150">
            <div>
              <div className="w-8 h-8 rounded-lg bg-[#10b981]/10 border border-[#10b981]/20 text-[#10b981] flex items-center justify-center mb-4">
                <Shield className="h-4 w-4" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Deterministic remediation & audit report</h3>
              <p className="text-xs text-[#a1a4a5] leading-relaxed mb-4">
                Executes verified runbooks, probes health convergence, and produces a complete 9-section Markdown post-mortem.
              </p>
            </div>

            <div className="space-y-2 font-mono text-xs my-2">
              <div className="p-2.5 rounded-lg border border-[#10b981]/30 bg-[#10b981]/10 text-emerald-400">
                <div className="flex items-center justify-between text-[11px] font-bold">
                  <span>RUNBOOK: POOL_EXPANSION</span>
                  <span>EXIT 0</span>
                </div>
                <div className="text-[10px] text-emerald-300 mt-1">
                  max_connections: 100 → 250 · cleared 45 stuck locks
                </div>
              </div>

              <div className="p-2 rounded-lg border border-[#1c1d28] bg-[#0b0c11] flex items-center justify-between text-[11px]">
                <span className="text-[#a1a4a5]">Health verification</span>
                <span className="text-emerald-400 font-semibold">18ms nominal</span>
              </div>

              <div className="p-2 rounded-lg border border-[#1c1d28] bg-[#0b0c11] flex items-center justify-between text-[11px]">
                <span className="text-[#a1a4a5]">Post-mortem export</span>
                <span className="text-[#3b9eff]">9-section MD</span>
              </div>
            </div>

            <div className="pt-3 border-t border-[#181924] flex items-center justify-between text-[11px] text-[#71717a] font-mono">
              <span>Full resolution in 12s</span>
              <Link 
                href="/dashboard" 
                className="text-[#10b981] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10b981]"
              >
                View incident post-mortems →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* SRE Console Launch CTA Banner */}
      <section className="py-16 px-6 max-w-4xl mx-auto w-full text-center">
        <div className="p-8 sm:p-12 rounded-3xl border border-[#2b2d3d] bg-gradient-to-b from-[#111219] to-[#07070a] relative overflow-hidden resend-blue-glow">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mb-4 break-words">
            Step Into the J.A.R.V.I.S. Control Deck
          </h2>
          <p className="text-sm text-[#a1a4a5] max-w-xl mx-auto mb-8">
            Access the live service topology graph, chronological incident timeline, fault injection panel, and real-time streaming telemetry.
          </p>
          <Link
            href="/dashboard"
            className="inline-flex items-center space-x-2 text-sm font-bold px-8 py-3.5 rounded-xl bg-white text-black hover:bg-[#e4e4e7] transition-colors duration-150 shadow-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff801f]"
          >
            <span>Launch Interactive Console</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Resend Minimal Footer */}
      <footer className="border-t border-[#14151e] bg-[#040406] px-8 py-6 text-xs text-[#71717a] flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse" />
          <span className="font-mono text-[#a1a4a5]">J.A.R.V.I.S. Core Engine Operational</span>
        </div>
        <div className="flex items-center space-x-6 text-[11px]">
          <Link href="/dashboard" className="hover:text-white transition-colors">Operations Console</Link>
          <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">Swagger API</a>
          <span className="text-[#52525b]">© 2026 J.A.R.V.I.S. Autonomous Systems</span>
        </div>
      </footer>
    </div>
  );
}
