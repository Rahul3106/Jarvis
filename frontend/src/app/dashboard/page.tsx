"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
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
  Trash2,
  ArrowRight,
  Download,
  AlertOctagon,
  Clock,
  Shield,
  Target,
  Zap,
  Menu,
  ChevronRight,
  ExternalLink,
  User,
  Rocket,
  Settings,
  GitBranch,
  Network,
  Share2,
  Upload,
  FileText,
  Send,
  X,
  TrendingDown,
  Users,
  DollarSign,
  Compass
} from "lucide-react";

// Get API base URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ServiceMetric {
  name: string;
  status: "healthy" | "unhealthy" | "offline";
  cpu: number; // ratio
  memory: number; // MB
  faults_injected: boolean;
}

interface Incident {
  id: string;
  service: string;
  alert_name: string;
  status: "INVESTIGATING" | "ROOT_CAUSE_FOUND" | "EXECUTING_FIX" | "VERIFYING" | "PENDING_APPROVAL" | "RESOLVED" | "FAILED";
  severity: string;
  root_cause?: string;
  confidence?: number;
  risk_level?: string;
  evidence?: string;
  affected_services?: string;
  reasoning_summary?: string;
  resolution_action?: string;
  resolution_time_seconds?: number;
  failed_transactions?: number;
  failed_logins?: number;
  impact_summary?: string;
  created_at: string;
  updated_at: string;
}

interface IncidentLog {
  id: number;
  incident_id: string;
  timestamp: string;
  level: "INFO" | "WARNING" | "ERROR" | "AGENT_THOUGHT" | "AGENT_ACTION" | "AGENT_RESULT";
  message: string;
}

interface CorrelatedEvent {
  id: string;
  incident_id?: string;
  source: string;
  service: string;
  event_type: string;
  severity: string;
  timestamp: string;
  message: string;
  trace_id?: string;
  raw_payload?: string;
  metadata_json?: string;
}

interface TimelineEntry {
  id: string;
  timestamp: string;
  phase: string;
  entry_type: string;
  source: string;
  service: string;
  severity: string;
  title: string;
  description: string;
  metadata?: any;
}

interface TimelineData {
  incident_id: string;
  service: string;
  alert_name: string;
  status: string;
  severity: string;
  total_timeline_entries: number;
  symptom_event_count: number;
  agent_log_count: number;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  services_involved: string[];
  spread_sequence: string[];
  impact: {
    failed_transactions: number;
    failed_logins: number;
    impact_summary: string;
  };
  timeline: TimelineEntry[];
}

// Seeding initial metrics to make history trends look beautiful instantly
const seedHistory = (currentVal: number, isCpu: boolean): number[] => {
  const samples: number[] = [];
  const count = 25;
  const stdDev = isCpu ? 0.04 : 3.0;
  for (let i = 0; i < count; i++) {
    const noise = (Math.random() + Math.random() + Math.random() - 1.5) * stdDev;
    const val = Math.max(0, currentVal + noise);
    samples.push(isCpu ? Math.min(1, val) : val);
  }
  return samples;
};

interface KdeChartProps {
  samples: number[];
  minVal: number;
  maxVal: number;
  label: string;
  colorClass: string;
  gradientId: string;
  valueSuffix: string;
  formatter: (v: number) => string;
}

function KdeChart({ samples, minVal, maxVal, label, colorClass, gradientId, valueSuffix, formatter }: KdeChartProps) {
  if (!samples || samples.length < 2) return null;

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const n = samples.length;
  const width = 280;
  const height = 90;
  const paddingBottom = 16;
  const chartHeight = height - paddingBottom;

  const range = maxVal - minVal || 1;
  const getY = (val: number) => {
    const clamped = Math.max(minVal, Math.min(maxVal, val));
    const ratio = (clamped - minVal) / range;
    return chartHeight - ratio * (chartHeight - 8);
  };

  const getX = (i: number) => (i / (n - 1)) * width;

  const points = samples.map((s, i) => ({ x: getX(i), y: getY(s), val: s }));

  let lineD = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const midX = (prev.x + curr.x) / 2;
    lineD += ` C ${midX} ${prev.y}, ${midX} ${curr.y}, ${curr.x} ${curr.y}`;
  }

  const areaD = `${lineD} L ${width} ${chartHeight} L 0 ${chartHeight} Z`;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, mouseX / rect.width));
    const idx = Math.round(ratio * (n - 1));
    setHoveredIdx(idx);
  };

  const handleMouseLeave = () => {
    setHoveredIdx(null);
  };

  const hoveredVal = hoveredIdx !== null ? samples[hoveredIdx] : null;
  const hoveredX = hoveredIdx !== null ? getX(hoveredIdx) : null;
  const hoveredY = hoveredVal !== null ? getY(hoveredVal) : null;

  const latestValue = samples[samples.length - 1];
  const isCpu = label.toLowerCase().includes("cpu");

  return (
    <div className="flex flex-col space-y-1.5 w-full">
      <div className="flex justify-between items-center text-[9px] font-bold tracking-normal font-medium text-slate-400">
        <span className="flex items-center gap-1">
          <span className={`h-1.5 w-1.5 rounded-full ${isCpu ? "bg-[#1488fc]" : "bg-[#818cf8]"}`}></span>
          {label} Trend
        </span>
        <span className="font-mono text-white bg-[#151722] px-2 py-0.5 rounded border border-[#272a3a] shadow-sm text-[10px]">
          Current: {formatter(latestValue)}{valueSuffix}
        </span>
      </div>

      <div className="relative h-[90px] w-full">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full overflow-visible cursor-crosshair"
          preserveAspectRatio="none"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={isCpu ? "#1488fc" : "#818cf8"} stopOpacity="0.25" />
              <stop offset="100%" stopColor={isCpu ? "#1488fc" : "#818cf8"} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          <line x1="0" y1={chartHeight * 0.25} x2={width} y2={chartHeight * 0.25} stroke="#1b1e2b" strokeWidth="1" />
          <line x1="0" y1={chartHeight * 0.5} x2={width} y2={chartHeight * 0.5} stroke="#1b1e2b" strokeWidth="1" />
          <line x1="0" y1={chartHeight * 0.75} x2={width} y2={chartHeight * 0.75} stroke="#1b1e2b" strokeWidth="1" />
          <line x1="0" y1={chartHeight} x2={width} y2={chartHeight} stroke="#282c3f" strokeWidth="1.5" />

          <text x={4} y={12} fill="#64748b" fontSize="8" fontFamily="monospace" className="opacity-80 font-bold">{formatter(maxVal)}{valueSuffix}</text>
          <text x={4} y={chartHeight - 4} fill="#64748b" fontSize="8" fontFamily="monospace" className="opacity-80 font-bold">{formatter(minVal)}{valueSuffix}</text>

          <path d={areaD} fill={`url(#${gradientId})`} />
          <path d={lineD} fill="none" stroke={isCpu ? "#1488fc" : "#818cf8"} strokeWidth="1.5" strokeLinecap="round" />

          <circle cx={width} cy={getY(latestValue)} r="3" fill={isCpu ? "#1488fc" : "#818cf8"} stroke="#000000" strokeWidth="1.5" />
          <circle cx={width} cy={getY(latestValue)} r="7" fill={isCpu ? "#1488fc" : "#818cf8"} className="animate-ping opacity-35 pointer-events-none" />

          {hoveredX !== null && hoveredY !== null && (
            <>
              <line
                x1={hoveredX}
                y1={0}
                x2={hoveredX}
                y2={chartHeight}
                stroke={isCpu ? "#3b82f6" : "#6366f1"}
                strokeWidth="1.2"
                strokeDasharray="3,3"
              />
              <circle
                cx={hoveredX}
                cy={hoveredY}
                r="4"
                fill={isCpu ? "#2563eb" : "#4f46e5"}
                stroke="#ffffff"
                strokeWidth="1.5"
              />
            </>
          )}
        </svg>

        {hoveredIdx !== null && hoveredVal !== null && hoveredX !== null && hoveredY !== null && (
          <div
            className="absolute z-10 pointer-events-none bg-slate-900/95 text-white font-mono text-[9px] px-2 py-1.5 rounded shadow-lg border border-slate-700/80 flex flex-col space-y-0.5 min-w-[95px] backdrop-blur-sm transition-all duration-75"
            style={{
              left: `${(hoveredX / width) * 100}%`,
              top: `${(hoveredY / height) * 100}%`,
              transform: hoveredX > width / 2 ? "translate(-110%, -110%)" : "translate(10%, -110%)",
            }}
          >
            <div className="flex justify-between gap-2 text-slate-400 font-bold border-b border-slate-700/50 pb-0.5 mb-0.5">
              <span>VAL</span>
              <span className="text-white">{formatter(hoveredVal)}{valueSuffix}</span>
            </div>
            <div className="flex justify-between gap-2 text-slate-400">
              <span>TIME</span>
              <span className="text-blue-300 font-bold">
                {hoveredIdx === n - 1 ? "Now" : `t-${n - 1 - hoveredIdx}`}
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="flex justify-between text-[8px] font-mono text-slate-400 px-0.5">
        <span>History Start</span>
        <span>Live</span>
      </div>
    </div>
  );
}

// ── Causal Topology Graph Visualizer (Phase 6) ─────────────────────────
interface TopologyGraphProps {
  affectedServices: string[];
  rootCauseService?: string;
  activeIncidentAlert?: string;
}

function CausalTopologyGraph({ affectedServices, rootCauseService, activeIncidentAlert }: TopologyGraphProps) {
  const isSaturated = (rootCauseService?.includes("database") || activeIncidentAlert?.includes("DatabaseSaturation"));

  // Check state of each node
  const getNodeState = (nodeName: string) => {
    if (nodeName === "database-service") {
      if (isSaturated || affectedServices.includes("database-service")) return "root_cause";
      return "nominal";
    }
    if (affectedServices.includes(nodeName)) return "degraded";
    return "nominal";
  };

  const nodes = [
    { id: "api-gateway", label: "API Gateway", x: 260, y: 35, role: "Edge Gateway" },
    { id: "user-service", label: "User Service", x: 100, y: 130, role: "Auth & Profiles" },
    { id: "order-service", label: "Order Service", x: 420, y: 130, role: "Checkout & Cart" },
    { id: "database-service", label: "PostgreSQL Primary", x: 260, y: 220, role: "Shared DB (Port 5432)" },
    { id: "payment-service", label: "Payment Service", x: 420, y: 310, role: "Ledger Transactions" },
    { id: "notification-service", label: "Notification", x: 570, y: 310, role: "Email & Webhooks" }
  ];

  return (
    <div className="relative w-full h-[360px] bg-slate-950 rounded-xl border border-slate-800 p-3 overflow-hidden flex flex-col">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-2">
        <div className="flex items-center space-x-2">
          <Network className="h-4 w-4 text-cyan-400 animate-pulse" />
          <span className="text-xs font-bold tracking-normal font-medium text-slate-200">
            Causal Dependency & Call Graph
          </span>
        </div>
        <div className="flex items-center space-x-3 text-[9px] font-mono">
          <span className="flex items-center gap-1 text-red-400 font-bold">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-ping"></span>
            ROOT CAUSE
          </span>
          <span className="flex items-center gap-1 text-amber-400 font-bold">
            <span className="h-2 w-2 rounded-full bg-amber-500"></span>
            DEGRADED
          </span>
          <span className="flex items-center gap-1 text-emerald-400 font-bold">
            <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
            NOMINAL
          </span>
        </div>
      </div>

      <div className="relative flex-1 w-full h-full">
        <svg viewBox="0 0 660 360" className="w-full h-full overflow-visible">
          {/* Call Graph Edges (Solid Lines) */}
          <line x1="260" y1="45" x2="110" y2="120" stroke="#334155" strokeWidth="2" strokeDasharray="4 2" />
          <line x1="260" y1="45" x2="410" y2="120" stroke="#334155" strokeWidth="2" strokeDasharray="4 2" />
          <line x1="420" y1="145" x2="420" y2="300" stroke="#334155" strokeWidth="2" />
          <line x1="430" y1="315" x2="560" y2="315" stroke="#334155" strokeWidth="2" />

          {/* Shared Infrastructure Dependency Links to Database (Glow colored) */}
          <line
            x1="110" y1="140" x2="250" y2="215"
            stroke={isSaturated ? "#ef4444" : "#0284c7"}
            strokeWidth={isSaturated ? "2.5" : "1.5"}
            strokeDasharray={isSaturated ? "5 3" : "none"}
            className={isSaturated ? "animate-pulse" : ""}
          />
          <line
            x1="410" y1="140" x2="270" y2="215"
            stroke={isSaturated ? "#ef4444" : "#0284c7"}
            strokeWidth={isSaturated ? "2.5" : "1.5"}
            strokeDasharray={isSaturated ? "5 3" : "none"}
            className={isSaturated ? "animate-pulse" : ""}
          />
          <line
            x1="410" y1="310" x2="270" y2="230"
            stroke={isSaturated ? "#ef4444" : "#0284c7"}
            strokeWidth={isSaturated ? "2.5" : "1.5"}
            strokeDasharray={isSaturated ? "5 3" : "none"}
            className={isSaturated ? "animate-pulse" : ""}
          />

          {/* Render Nodes */}
          {nodes.map(n => {
            const state = getNodeState(n.id);
            const isRoot = state === "root_cause";
            const isDegraded = state === "degraded";

            let fill = "#0f172a";
            let stroke = "#334155";
            let badgeBg = "bg-slate-800 text-slate-400";
            let badgeText = "OK";

            if (isRoot) {
              fill = "#450a0a";
              stroke = "#ef4444";
              badgeBg = "bg-red-500 text-white animate-pulse";
              badgeText = "ROOT CAUSE";
            } else if (isDegraded) {
              fill = "#451a03";
              stroke = "#f59e0b";
              badgeBg = "bg-amber-500 text-black";
              badgeText = "DEGRADED";
            } else {
              fill = "#064e3b";
              stroke = "#10b981";
              badgeBg = "bg-emerald-500/20 text-emerald-300";
              badgeText = "HEALTHY";
            }

            return (
              <g key={n.id} className="cursor-pointer transition-transform hover:scale-105">
                {isRoot && (
                  <circle cx={n.x} cy={n.y} r="35" fill="none" stroke="#ef4444" strokeWidth="2" className="animate-ping opacity-40 pointer-events-none" />
                )}
                <rect
                  x={n.x - 65}
                  y={n.y - 25}
                  width="130"
                  height="50"
                  rx="8"
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={isRoot ? "2.5" : "1.5"}
                />
                <text x={n.x} y={n.y - 6} fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle" fontFamily="sans-serif">
                  {n.label}
                </text>
                <text x={n.x} y={n.y + 8} fill="#94a3b8" fontSize="7.5" textAnchor="middle" fontFamily="monospace">
                  {n.role}
                </text>
                <foreignObject x={n.x - 45} y={n.y + 13} width="90" height="15">
                  <div className="flex justify-center">
                    <span className={`text-[7px] px-1.5 py-0.2 rounded font-mono font-bold tracking-wider ${badgeBg}`}>
                      {badgeText}
                    </span>
                  </div>
                </foreignObject>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-1 pt-1 border-t border-slate-800/80 text-[10px] text-slate-400 flex items-center justify-between">
        <span>Shared Resource: <strong className="text-cyan-300 font-mono">database-service (postgres-primary)</strong></span>
        <span>Call Propagation: <strong className="text-slate-300">Gateway &rarr; Services &rarr; Database</strong></span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [services, setServices] = useState<Record<string, ServiceMetric>>({});
  const [telemetryHistory, setTelemetryHistory] = useState<Record<string, { cpu: number[]; memory: number[] }>>({});
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [logs, setLogs] = useState<IncidentLog[]>([]);
  const [loadingServices, setLoadingServices] = useState(true);
  const [injectingFault, setInjectingFault] = useState<string | null>(null);
  const [clearingFaults, setClearingFaults] = useState(false);
  const [triggeringRisk, setTriggeringRisk] = useState<string | null>(null);
  const [filterActive, setFilterActive] = useState(false);

  // Phase 5 & 6 Interactive Additions
  const [activeTab, setActiveTab] = useState<"overview" | "topology" | "timeline" | "events" | "terminal" | "report">("overview");
  const [timelineData, setTimelineData] = useState<TimelineData | null>(null);
  const [correlatedEvents, setCorrelatedEvents] = useState<CorrelatedEvent[]>([]);
  const [showIngestionModal, setShowIngestionModal] = useState(false);
  const [uploadingLog, setUploadingLog] = useState(false);
  const [selectedLogFile, setSelectedLogFile] = useState<File | null>(null);
  const [modalUploadStatus, setModalUploadStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [ingestionNotification, setIngestionNotification] = useState<string | null>(null);

  // Manual event emission form state
  const [manualEventService, setManualEventService] = useState("user-service");
  const [manualEventSource, setManualEventSource] = useState("api");
  const [manualEventSeverity, setManualEventSeverity] = useState("error");
  const [manualEventMessage, setManualEventMessage] = useState("DatabaseSaturation: User auth connection checkout timed out");

  const consoleRef = useRef<HTMLDivElement>(null);
  const prevIncidentIdRef = useRef<string | null>(null);

  const handleTelemetryUpdate = (data: Record<string, ServiceMetric>) => {
    setServices(data);
    setTelemetryHistory(prev => {
      const nextHistory = { ...prev };
      Object.keys(data).forEach(name => {
        const svc = data[name];
        const cpuVal = svc.cpu;
        const memVal = svc.memory;

        if (!nextHistory[name]) {
          nextHistory[name] = {
            cpu: seedHistory(cpuVal, true),
            memory: seedHistory(memVal, false)
          };
        } else {
          const currentCpu = [...nextHistory[name].cpu, cpuVal];
          const currentMem = [...nextHistory[name].memory, memVal];
          if (currentCpu.length > 40) currentCpu.shift();
          if (currentMem.length > 40) currentMem.shift();
          nextHistory[name] = {
            cpu: currentCpu,
            memory: currentMem
          };
        }
      });
      return nextHistory;
    });
    setLoadingServices(false);
  };

  // Poll SRE incidents
  useEffect(() => {
    const fetchIncidents = async () => {
      try {
        const iRes = await fetch(`${API_URL}/api/v1/incidents`);
        if (iRes.ok) {
          const data = await iRes.json();
          setIncidents(data);

          if (!selectedIncidentId && data.length > 0) {
            const activeIncident = data.find((inc: Incident) =>
              ["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"].includes(inc.status)
            );
            if (activeIncident) {
              setSelectedIncidentId(activeIncident.id);
            } else {
              setSelectedIncidentId(data[0].id);
            }
          }
        }
      } catch (err) {
        console.error("Failed to fetch incidents list:", err);
      }
    };

    fetchIncidents();
    const interval = setInterval(fetchIncidents, 3000);
    return () => clearInterval(interval);
  }, [selectedIncidentId]);

  // Real-time Telemetry Subscription: WebSocket with HTTP fallback
  useEffect(() => {
    let ws: WebSocket | null = null;
    let fallbackInterval: any = null;
    let isConnected = false;

    const startFallbackPolling = () => {
      if (fallbackInterval) return;
      console.log("WebSocket inactive – starting HTTP status polling fallback (2s)");

      const poll = async () => {
        try {
          const res = await fetch(`${API_URL}/api/v1/simulation/status`);
          if (res.ok) {
            const data = await res.json();
            handleTelemetryUpdate(data);
          }
        } catch (err) {
          console.error("HTTP status polling failed:", err);
        }
      };

      poll();
      fallbackInterval = setInterval(poll, 2000);
    };

    const stopFallbackPolling = () => {
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
        fallbackInterval = null;
      }
    };

    const connectWs = () => {
      try {
        const wsUrl = API_URL.replace(/^http/, "ws") + "/api/v1/simulation/ws";
        console.log(`Connecting to SRE Telemetry WebSocket: ${wsUrl}`);
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log("Telemetry WebSocket connected – real-time 500ms push active");
          isConnected = true;
          stopFallbackPolling();
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            handleTelemetryUpdate(data);
          } catch (err) {
            console.error("Failed to parse telemetry WebSocket data:", err);
          }
        };

        ws.onerror = (err) => {
          console.warn("Telemetry WebSocket error, falling back to REST:", err);
          if (!isConnected) {
            startFallbackPolling();
          }
        };

        ws.onclose = () => {
          console.log("Telemetry WebSocket closed");
          isConnected = false;
          startFallbackPolling();
          setTimeout(() => {
            if (!isConnected) connectWs();
          }, 5000);
        };
      } catch (err) {
        console.error("WebSocket setup failed:", err);
        startFallbackPolling();
      }
    };

    connectWs();

    return () => {
      if (ws) ws.close();
      stopFallbackPolling();
    };
  }, []);

  // Poll logs, timeline, and correlated events when an incident is selected
  useEffect(() => {
    if (!selectedIncidentId) {
      setLogs([]);
      setTimelineData(null);
      setCorrelatedEvents([]);
      return;
    }

    const fetchIncidentDetails = async () => {
      try {
        // Fetch Logs
        const logRes = await fetch(`${API_URL}/api/v1/incidents/${selectedIncidentId}/logs`);
        if (logRes.ok) {
          const lData = await logRes.json();
          setLogs(lData);
        }

        // Fetch Timeline
        const tlRes = await fetch(`${API_URL}/api/v1/incidents/${selectedIncidentId}/timeline`);
        if (tlRes.ok) {
          const tData = await tlRes.json();
          setTimelineData(tData);
        }

        // Fetch Correlated Events
        const ceRes = await fetch(`${API_URL}/api/v1/incidents/${selectedIncidentId}/correlated-events`);
        if (ceRes.ok) {
          const ceData = await ceRes.json();
          setCorrelatedEvents(ceData.events || []);
        }
      } catch (err) {
        console.error("Failed to fetch incident details/timeline:", err);
      }
    };

    fetchIncidentDetails();
    const interval = setInterval(fetchIncidentDetails, 2000);
    return () => clearInterval(interval);
  }, [selectedIncidentId]);

  // Auto-scroll logs terminal container only
  useEffect(() => {
    if (consoleRef.current) {
      const container = consoleRef.current;
      const incidentChanged = prevIncidentIdRef.current !== selectedIncidentId;

      if (incidentChanged) {
        container.scrollTop = container.scrollHeight;
        prevIncidentIdRef.current = selectedIncidentId;
      } else {
        const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= 100;
        if (isNearBottom) {
          container.scrollTop = container.scrollHeight;
        }
      }
    }
  }, [logs, selectedIncidentId]);

  const injectFault = async (service: string, fault: string) => {
    setInjectingFault(`${service}-${fault}`);
    try {
      const res = await fetch(`${API_URL}/api/v1/simulation/inject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service, fault })
      });
      if (res.ok) {
        console.log(`Fault ${fault} injected into ${service}.`);
      }
    } catch (err) {
      console.error("Failed to inject fault:", err);
    } finally {
      setInjectingFault(null);
    }
  };

  const triggerTestIncident = async (risk: "low" | "medium" | "high" | "critical") => {
    setTriggeringRisk(risk);
    try {
      const res = await fetch(`${API_URL}/api/v1/simulation/trigger-test-incident`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ risk })
      });
      if (res.ok) {
        const data = await res.json();
        console.log(`Test incident triggered:`, data);
        if (data.incident_id) {
          setSelectedIncidentId(data.incident_id);
        }
      }
    } catch (err) {
      console.error("Failed to trigger test incident:", err);
    } finally {
      setTriggeringRisk(null);
    }
  };

  // 1-Click J.A.R.V.I.S. Challenge Scenario Runner
  const runPaymentPlatformScenario = async () => {
    setScenarioLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/simulation/scenario/payment-platform-outage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          inject_mock_faults: true,
          trigger_background_agent: true
        })
      });
      if (res.ok) {
        const data = await res.json();
        setIngestionNotification(`Triggered J.A.R.V.I.S. Payment Outage Scenario! Master Incident: ${data.master_incident_id}`);
        if (data.master_incident_id) {
          setSelectedIncidentId(data.master_incident_id);
          setActiveTab("overview");
        }
      }
    } catch (err) {
      console.error("Failed to run scenario:", err);
    } finally {
      setScenarioLoading(false);
    }
  };

  // Handle Log File Selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setSelectedLogFile(file);
    setModalUploadStatus(null);
  };

  // Upload Log File Handler (Triggered by Run Button)
  const handleFileUpload = async () => {
    if (!selectedLogFile) return;

    setUploadingLog(true);
    setModalUploadStatus(null);
    const formData = new FormData();
    formData.append("file", selectedLogFile);

    try {
      const res = await fetch(`${API_URL}/api/v1/logs/upload`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        const correlatedCount = data.events_correlated ?? data.grouped_with_incident ?? 0;
        const successMsg = `Uploaded ${selectedLogFile.name}: Ingested ${data.events_ingested} events (${correlatedCount} correlated).`;
        setModalUploadStatus({ type: "success", message: successMsg });
        setIngestionNotification(successMsg);

        if (data.master_incident_id) {
          setSelectedIncidentId(data.master_incident_id);
          setActiveTab("events");
          setTimeout(() => setShowIngestionModal(false), 900);
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        setModalUploadStatus({ type: "error", message: errData.detail || "Failed to parse and ingest log file." });
      }
    } catch (err) {
      console.error("Failed to upload logs:", err);
      setModalUploadStatus({ type: "error", message: "Network error connecting to J.A.R.V.I.S. backend." });
    } finally {
      setUploadingLog(false);
    }
  };

  // Manual Event Emission Handler
  const handleManualEventEmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_URL}/api/v1/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service: manualEventService,
          source: manualEventSource,
          severity: manualEventSeverity,
          message: manualEventMessage
        })
      });
      if (res.ok) {
        const data = await res.json();
        setIngestionNotification(`Event emitted: ${data.event.id} (Action: ${data.correlation.action})`);
      }
    } catch (err) {
      console.error("Failed to emit event:", err);
    }
  };

  const clearAllFaults = async () => {
    setClearingFaults(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/simulation/clear`, {
        method: "POST"
      });
      if (res.ok) {
        console.log("All faults cleared.");
      }
    } catch (err) {
      console.error("Failed to clear faults:", err);
    } finally {
      setClearingFaults(false);
    }
  };

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return isoString;
    }
  };

  const parseJsonField = (jsonStr?: string): any[] => {
    if (!jsonStr) return [];
    try {
      const parsed = JSON.parse(jsonStr);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  const getRiskColor = (risk?: string) => {
    switch (risk?.toUpperCase()) {
      case "CRITICAL": return { border: "border-red-300", bg: "bg-red-500/10", text: "text-red-600" };
      case "HIGH": return { border: "border-orange-300", bg: "bg-orange-500/10", text: "text-orange-600" };
      case "MEDIUM": return { border: "border-amber-300", bg: "bg-amber-500/10", text: "text-amber-600" };
      case "LOW": return { border: "border-emerald-300", bg: "bg-emerald-500/10", text: "text-emerald-600" };
      default: return { border: "border-slate-300", bg: "bg-slate-500/10", text: "text-slate-600" };
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "healthy": return "text-emerald-600 border-emerald-100 bg-emerald-50";
      case "unhealthy": return "text-red-600 border-red-100 bg-red-50";
      default: return "text-slate-500 border-slate-100 bg-slate-50";
    }
  };

  const getIncidentStatusBadge = (status: string) => {
    switch (status) {
      case "INVESTIGATING":
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-purple-200 bg-purple-50 text-purple-600 animate-pulse">INVESTIGATING</span>;
      case "ROOT_CAUSE_FOUND":
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-indigo-200 bg-indigo-50 text-indigo-600 animate-pulse">DIAGNOSING</span>;
      case "EXECUTING_FIX":
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-amber-200 bg-amber-50 text-amber-600 animate-pulse">REMEDIATING</span>;
      case "VERIFYING":
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-cyan-200 bg-cyan-50 text-cyan-600 animate-pulse">VERIFYING</span>;
      case "PENDING_APPROVAL":
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-orange-200 bg-orange-50 text-orange-700 animate-pulse">PENDING APPROVAL</span>;
      case "RESOLVED":
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-emerald-200 bg-emerald-50 text-emerald-600">RESOLVED</span>;
      default:
        return <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border border-red-200 bg-red-50 text-red-600">FAILED</span>;
    }
  };

  const getLogStyle = (level: string) => {
    switch (level) {
      case "AGENT_THOUGHT":
        return "text-cyan-300 italic font-mono";
      case "AGENT_ACTION":
        return "text-amber-400 font-semibold font-mono";
      case "AGENT_RESULT":
        return "text-slate-300 font-mono bg-slate-900/60 p-2.5 rounded border border-slate-800 my-1.5 block whitespace-pre-wrap text-[11px]";
      case "ERROR":
        return "text-red-400 font-semibold font-mono animate-pulse";
      case "WARNING":
        return "text-amber-400 font-mono";
      default:
        return "text-slate-300 font-mono";
    }
  };

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case "DETECTION": return "bg-rose-500/10 text-rose-600 border-rose-200";
      case "CORRELATION": return "bg-purple-500/10 text-purple-600 border-purple-200";
      case "TELEMETRY": return "bg-blue-500/10 text-blue-600 border-blue-200";
      case "DIAGNOSIS": return "bg-indigo-500/10 text-indigo-600 border-indigo-200";
      case "GOVERNANCE": return "bg-amber-500/10 text-amber-600 border-amber-200";
      case "REMEDIATION": return "bg-cyan-500/10 text-cyan-600 border-cyan-200";
      case "VERIFICATION": return "bg-teal-500/10 text-teal-600 border-teal-200";
      case "RECOVERY": return "bg-emerald-500/10 text-emerald-600 border-emerald-200";
      default: return "bg-slate-500/10 text-slate-600 border-slate-200";
    }
  };

  const selectedIncident = incidents.find(inc => inc.id === selectedIncidentId);
  const activeIncidentsCount = incidents.filter(inc => ["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"].includes(inc.status)).length;
  const clusterIsHealthy = Object.values(services).every(s => s.status === "healthy");

  const filteredIncidents = filterActive
    ? incidents.filter(inc => ["INVESTIGATING", "ROOT_CAUSE_FOUND", "EXECUTING_FIX", "VERIFYING", "PENDING_APPROVAL"].includes(inc.status))
    : incidents;

  const affectedServicesList = selectedIncident ? parseJsonField(selectedIncident.affected_services) : [];

  return (
    <div className="relative min-h-screen bg-[#090a0f] text-[#fcfdff] flex flex-col font-sans overflow-x-hidden">
      {/* Bolt.new Top Ambient Cockpit Flare */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1200px] h-[350px] bg-gradient-to-b from-[#1488fc]/10 via-transparent to-transparent pointer-events-none -z-10" />

      {/* Ingestion Notification Banner */}
      {ingestionNotification && (
        <div className="bg-[#1488fc] text-white text-xs px-6 py-2.5 flex items-center justify-between sticky top-0 z-50 shadow-lg shadow-[#1488fc]/20">
          <div className="flex items-center space-x-2">
            <Zap className="h-4 w-4 text-cyan-200 animate-pulse" />
            <span className="font-semibold">{ingestionNotification}</span>
          </div>
          <button onClick={() => setIngestionNotification(null)} className="hover:opacity-75 cursor-pointer">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Top Cockpit Navbar */}
      <header className="border-b border-[#1b1e2c] bg-[#0c0d14]/90 backdrop-blur-md px-6 md:px-8 py-3.5 flex items-center justify-between sticky top-0 z-40">
        <Link href="/" className="flex items-center space-x-3 cursor-pointer group">
          <div className="p-2 rounded-lg bg-[#1488fc]/10 border border-[#1488fc]/30 text-[#1488fc] group-hover:bg-[#1488fc] group-hover:text-white transition-all duration-200">
            <Activity className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <h1 className="text-base font-heading font-black tracking-tight text-white flex items-center space-x-2">
              <span>J.A.R.V.I.S.</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 tracking-normal font-semibold font-mono">
                SRE COCKPIT
              </span>
            </h1>
          </div>
        </Link>

        {/* Center menu navigation links */}
        <nav className="hidden md:flex space-x-8 text-xs font-bold tracking-wider text-[#a1a4a5] font-sans">
          <Link href="/" className="hover:text-white transition-colors uppercase">Home</Link>
          <Link href="/dashboard" className="text-[#38bdf8] transition-colors uppercase font-extrabold border-b-2 border-[#1488fc] pb-1">Console</Link>
          <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors uppercase flex items-center gap-1">
            <span>API Docs</span>
            <ExternalLink className="h-3 w-3" />
          </a>
        </nav>

        <div className="flex items-center space-x-3">
          {/* J.A.R.V.I.S. Payment Outage Challenge Scenario Button */}
          <button
            onClick={runPaymentPlatformScenario}
            disabled={scenarioLoading}
            className="flex items-center space-x-1.5 px-4 py-2 text-xs font-bold tracking-wider bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white rounded-lg transition-all duration-200 disabled:opacity-50 shadow-md shadow-rose-900/30 cursor-pointer animate-pulse"
          >
            <Play className="h-3 w-3 fill-current" />
            <span>{scenarioLoading ? "Triggering..." : "Challenge Scenario"}</span>
          </button>

          {/* Ingestion Console Modal Toggle */}
          <button
            onClick={() => setShowIngestionModal(true)}
            className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold tracking-wider bg-[#141622] hover:bg-[#1d2030] text-[#d1d5db] hover:text-white rounded-lg transition-all cursor-pointer border border-[#26293b]"
          >
            <Upload className="h-3 w-3 text-[#1488fc]" />
            <span>Ingest Data</span>
          </button>

          {/* Reset button */}
          <button
            onClick={clearAllFaults}
            disabled={clearingFaults}
            className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold tracking-wider border border-[#26293b] text-[#a1a4a5] hover:bg-[#141622] hover:text-white rounded-lg transition-all duration-200 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${clearingFaults ? "animate-spin" : ""}`} />
            <span>Reset</span>
          </button>
        </div>
      </header>

      {/* SRE Operations Center */}
      <main id="ops-center" className="flex-grow px-6 md:px-8 py-6 max-w-[1550px] mx-auto w-full space-y-5">

        {/* Header Summary */}
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
              <h2 className="text-xs tracking-normal font-semibold font-black text-[#1488fc]">J.A.R.V.I.S. Control Deck</h2>
            </div>
            <h3 className="font-heading font-black text-white text-2xl tracking-tight">
              Cross-Service Incident Correlation & Root Cause Cockpit
            </h3>
            <p className="text-[#a1a4a5] text-xs mt-1">
              Real-time multi-source telemetry, topological causal graph, cross-service incident grouping, and autonomous remediation.
            </p>
          </div>

          <div className="flex items-center gap-3 bg-[#11131c] p-3 rounded-xl border border-[#1e2130] shadow-sm text-xs">
            <div className="flex flex-col">
              <span className="text-[10px] text-[#71717a] font-bold tracking-normal font-medium">Active Outages</span>
              <span className="font-bold text-white">{activeIncidentsCount} Ongoing Investigations</span>
            </div>
            <div className={`p-2 rounded-lg ${activeIncidentsCount === 0 ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-red-500/10 text-red-400 border border-red-500/20 animate-pulse"}`}>
              <Server className="h-4 w-4" />
            </div>
          </div>
        </div>

        {/* Real-time Telemetry Profiles */}
        <div className="bg-[#0d0e15] border border-[#1b1e2c] rounded-2xl p-4 w-full shadow-xl">
          <div className="flex items-center justify-between mb-3 border-b border-[#181a26] pb-2">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#1488fc] animate-ping"></span>
              <h4 className="text-xs font-bold tracking-normal font-semibold text-[#d1d5db] flex items-center gap-1.5">
                <Activity className="h-4 w-4 text-[#1488fc]" />
                <span>Live Cluster Telemetry Trends</span>
              </h4>
            </div>
            <span className="text-[10px] text-[#71717a] font-mono">Sliding window • 500ms sampling</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {Object.values(services).map((service) => {
              const history = telemetryHistory[service.name];
              if (!history) return null;

              return (
                <div
                  key={service.name}
                  className="bg-[#12141e] border border-[#1e2232] rounded-xl p-3 flex flex-col space-y-2 relative hover:border-[#2f354c] transition-all"
                >
                  <div className="flex items-center justify-between border-b border-[#1c1f2e] pb-1.5">
                    <span className="font-heading font-black text-[11px] text-white uppercase tracking-tight">{service.name}</span>
                    <span className={`px-1.5 py-0.5 text-[8px] font-bold tracking-wider rounded border ${getStatusColor(service.status)}`}>
                      {service.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="flex flex-col space-y-2">
                    <KdeChart
                      samples={history.cpu}
                      minVal={0}
                      maxVal={1.0}
                      label="CPU"
                      colorClass="text-blue-600"
                      gradientId={`global-cpu-kde-${service.name}`}
                      valueSuffix="%"
                      formatter={(v) => (v * 100).toFixed(0)}
                    />
                    <KdeChart
                      samples={history.memory}
                      minVal={0}
                      maxVal={120}
                      label="MEM"
                      colorClass="text-indigo-600"
                      gradientId={`global-mem-kde-${service.name}`}
                      valueSuffix="MB"
                      formatter={(v) => v.toFixed(0)}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 3-Panel Operations Workspace (Bolt.new Cockpit) */}
        <div className="bg-[#0b0c12] border border-[#1b1e2c] shadow-[0_15px_50px_rgba(0,0,0,0.5)] rounded-2xl overflow-hidden flex flex-col lg:flex-row lg:h-[730px] w-full divide-y lg:divide-y-0 lg:divide-x divide-[#1b1e2c]">

          {/* Panel 1: Fault Simulation Injector */}
          <div className="w-full lg:w-[25%] flex flex-col h-[500px] lg:h-full overflow-hidden bg-[#0a0b10]">
            <div className="p-3.5 bg-[#0e1017] border-b border-[#1b1e2c] flex items-center justify-between">
              <h4 className="text-xs font-bold tracking-normal font-medium text-[#a1a4a5] flex items-center space-x-1.5">
                <Flame className="h-4 w-4 text-rose-500" />
                <span>Simulated Services</span>
              </h4>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {Object.values(services).map((service) => (
                <div
                  key={service.name}
                  className="p-3 bg-[#11131d] border border-[#1e2232] rounded-xl flex flex-col space-y-2 hover:border-[#2f354c] transition-all"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[11px] text-white">{service.name}</span>
                    <span className={`px-1.5 py-0.5 text-[8px] font-bold rounded border ${getStatusColor(service.status)}`}>
                      {service.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="space-y-1 text-[9px] text-[#71717a]">
                    <div className="flex justify-between">
                      <span>CPU: <strong className="text-white font-mono">{(service.cpu * 100).toFixed(0)}%</strong></span>
                      <span>MEM: <strong className="text-white font-mono">{service.memory.toFixed(0)} MB</strong></span>
                    </div>
                  </div>

                  <div className="pt-1.5 border-t border-[#1a1d2b] flex items-center gap-1 flex-wrap">
                    <button
                      onClick={() => injectFault(service.name, "memory-leak")}
                      disabled={injectingFault !== null || service.status === "offline"}
                      className="px-2 py-0.5 text-[8px] font-bold text-red-400 hover:text-white border border-red-500/30 hover:bg-red-500/20 rounded-md transition-all cursor-pointer"
                    >
                      Leak Mem
                    </button>
                    <button
                      onClick={() => injectFault(service.name, "cpu-spike")}
                      disabled={injectingFault !== null || service.status === "offline"}
                      className="px-2 py-0.5 text-[8px] font-bold text-amber-400 hover:text-white border border-amber-500/30 hover:bg-amber-500/20 rounded-md transition-all cursor-pointer"
                    >
                      Spike CPU
                    </button>
                    <button
                      onClick={() => injectFault(service.name, "db-saturation")}
                      disabled={injectingFault !== null || service.status === "offline"}
                      className="px-2 py-0.5 text-[8px] font-bold text-rose-400 hover:text-white border border-rose-500/30 hover:bg-rose-500/20 rounded-md transition-all cursor-pointer"
                    >
                      Sat DB
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Quick 4-tier risk injection test */}
            <div className="p-3 bg-[#07080c] border-t border-[#1b1e2c] text-white">
              <span className="text-[10px] font-bold tracking-normal font-medium text-[#71717a] block mb-1">
                Risk Gate Tests
              </span>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  onClick={() => triggerTestIncident("low")}
                  className="px-2 py-1 text-[9px] font-bold bg-[#11131c] hover:bg-[#1a1d2c] text-emerald-400 rounded-md cursor-pointer border border-[#232738]"
                >
                  Low Risk (Auto)
                </button>
                <button
                  onClick={() => triggerTestIncident("critical")}
                  className="px-2 py-1 text-[9px] font-bold bg-[#11131c] hover:bg-[#1a1d2c] text-rose-400 rounded-md cursor-pointer border border-[#232738]"
                >
                  Critical (Halt)
                </button>
              </div>
            </div>
          </div>

          {/* Panel 2: Correlated Incidents Feed */}
          <div className="w-full lg:w-[25%] flex flex-col h-[400px] lg:h-full overflow-hidden bg-[#0c0d14]">
            <div className="p-3.5 bg-[#0e1017] border-b border-[#1b1e2c] flex items-center justify-between">
              <h4 className="text-xs font-bold tracking-normal font-medium text-[#a1a4a5] flex items-center space-x-1.5">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <span>Correlated Incidents</span>
              </h4>
              <button
                onClick={() => setFilterActive(!filterActive)}
                className={`text-[9px] px-2 py-0.5 rounded-full border font-bold uppercase cursor-pointer ${filterActive ? "bg-[#1488fc] text-white border-[#1488fc]" : "border-[#272a3a] text-[#a1a4a5]"}`}
              >
                {filterActive ? "All" : "Active"}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {filteredIncidents.length === 0 ? (
                <div className="h-40 flex flex-col items-center justify-center text-[#71717a] text-center space-y-2 border border-dashed border-[#1f2233] rounded-xl">
                  <CheckCircle className="h-6 w-6 text-emerald-500" />
                  <span className="text-[10px] font-bold">No Active Incidents</span>
                </div>
              ) : (
                filteredIncidents.map((incident) => {
                  const isSelected = incident.id === selectedIncidentId;
                  const affected = parseJsonField(incident.affected_services);

                  return (
                    <div
                      key={incident.id}
                      onClick={() => setSelectedIncidentId(incident.id)}
                      className={`p-3 rounded-xl border text-left cursor-pointer transition-all flex flex-col space-y-2 ${isSelected
                        ? "bg-[#141b2e] border-[#1488fc]/60 shadow-md ring-1 ring-[#1488fc]/30"
                        : "bg-[#10121a] border-[#1b1e2b] hover:border-[#2b3045]"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[9px] font-bold text-[#818cf8]">{incident.id}</span>
                        {getIncidentStatusBadge(incident.status)}
                      </div>

                      <div>
                        <h4 className="font-bold text-xs text-white">{incident.alert_name}</h4>
                        <div className="text-[#a1a4a5] text-[9px] flex items-center gap-1 mt-0.5">
                          <span>Service:</span>
                          <span className="font-mono text-white font-semibold">{incident.service}</span>
                        </div>
                      </div>

                      {/* Correlated blast radius badges */}
                      {affected.length > 1 && (
                        <div className="flex items-center gap-1 flex-wrap pt-1">
                          <span className="px-1.5 py-0.2 text-[8px] bg-purple-500/10 text-purple-300 border border-purple-500/30 rounded-full font-bold">
                            {affected.length} Connected Services
                          </span>
                        </div>
                      )}

                      <div className="flex items-center justify-between pt-1.5 border-t border-[#1b1e2b] text-[9px] text-[#71717a]">
                        <span className="flex items-center space-x-1">
                          <Clock className="h-3 w-3" />
                          <span>{formatTime(incident.created_at)}</span>
                        </span>
                        {incident.failed_transactions ? (
                          <span className="text-rose-400 font-bold font-mono">
                            -{incident.failed_transactions} tx
                          </span>
                        ) : null}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Panel 3: Interactive J.A.R.V.I.S. Incident Intelligence Center */}
          <div className="w-full lg:w-[50%] flex flex-col h-[550px] lg:h-full overflow-hidden bg-[#090a0f]">
            {/* Tab Navigation */}
            <div className="p-3 bg-[#0e1017] border-b border-[#1b1e2c] flex items-center justify-between shrink-0">
              <div className="flex items-center space-x-1 overflow-x-auto">
                <button
                  onClick={() => setActiveTab("overview")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${activeTab === "overview" ? "bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 shadow-xs" : "text-[#8b90a0] hover:text-white"}`}
                >
                  Overview & Impact
                </button>
                <button
                  onClick={() => setActiveTab("topology")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1 ${activeTab === "topology" ? "bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 shadow-xs" : "text-[#8b90a0] hover:text-white"}`}
                >
                  <Network className="h-3 w-3" />
                  <span>Causal Graph</span>
                </button>
                <button
                  onClick={() => setActiveTab("timeline")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1 ${activeTab === "timeline" ? "bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 shadow-xs" : "text-[#8b90a0] hover:text-white"}`}
                >
                  <GitBranch className="h-3 w-3" />
                  <span>Timeline ({timelineData?.timeline?.length || 0})</span>
                </button>
                <button
                  onClick={() => setActiveTab("events")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1 ${activeTab === "events" ? "bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 shadow-xs" : "text-[#8b90a0] hover:text-white"}`}
                >
                  <Layers className="h-3 w-3" />
                  <span>Events ({correlatedEvents.length})</span>
                </button>
                <button
                  onClick={() => setActiveTab("terminal")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1 ${activeTab === "terminal" ? "bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 shadow-xs" : "text-[#8b90a0] hover:text-white"}`}
                >
                  <Terminal className="h-3 w-3" />
                  <span>Agent Stream</span>
                </button>
                <button
                  onClick={() => setActiveTab("report")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1 ${activeTab === "report" ? "bg-[#1488fc]/15 text-[#38bdf8] border border-[#1488fc]/30 shadow-xs" : "text-[#8b90a0] hover:text-white"}`}
                >
                  <FileText className="h-3 w-3" />
                  <span>Post-Mortem</span>
                </button>
              </div>

              {selectedIncident?.resolution_action && (
                <button
                  onClick={() => {
                    const element = document.createElement("a");
                    const file = new Blob([selectedIncident.resolution_action || ""], { type: 'text/markdown' });
                    element.href = URL.createObjectURL(file);
                    element.download = `PostMortem-${selectedIncident.id}.md`;
                    document.body.appendChild(element);
                    element.click();
                    document.body.removeChild(element);
                  }}
                  className="flex items-center space-x-1 px-2.5 py-1 text-[10px] font-bold rounded-lg bg-[#1488fc] text-white hover:bg-[#0c70d4] cursor-pointer shadow-xs"
                >
                  <Download className="h-3 w-3" />
                  <span>Post-Mortem</span>
                </button>
              )}
            </div>

            {selectedIncident ? (
              <div className="flex-1 flex flex-col p-4 overflow-y-auto space-y-4">

                {/* TAB 1: OVERVIEW & IMPACT */}
                {activeTab === "overview" && (
                  <div className="space-y-4">
                    {/* Master Incident Card Header */}
                    <div className="p-4 bg-[#11131d] border border-[#1e2232] rounded-xl space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-[#38bdf8]">{selectedIncident.id}</span>
                          <span className="text-[10px] bg-[#191c2b] text-[#cbd5e1] border border-[#272d42] px-2 py-0.5 rounded font-mono">
                            {selectedIncident.service}
                          </span>
                        </div>
                        {getIncidentStatusBadge(selectedIncident.status)}
                      </div>

                      {/* Quantified Business Impact Cards */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                        <div className="p-2.5 bg-[#250d15] border border-[#4a1827] rounded-lg">
                          <div className="text-[9px] font-bold tracking-normal font-medium text-rose-400 flex items-center gap-1">
                            <TrendingDown className="h-3 w-3" />
                            <span>Failed Tx</span>
                          </div>
                          <div className="text-xl font-black text-rose-300 font-mono mt-0.5">
                            {selectedIncident.failed_transactions || 0}
                          </div>
                          <span className="text-[8px] text-rose-400 font-bold">MEASURED TELEMETRY</span>
                        </div>

                        <div className="p-2.5 bg-[#251b0d] border border-[#4a3618] rounded-lg">
                          <div className="text-[9px] font-bold tracking-normal font-medium text-amber-400 flex items-center gap-1">
                            <Users className="h-3 w-3" />
                            <span>Failed Logins</span>
                          </div>
                          <div className="text-xl font-black text-amber-300 font-mono mt-0.5">
                            {selectedIncident.failed_logins || 0}
                          </div>
                          <span className="text-[8px] text-amber-400 font-bold">AUTH TIMEOUTS</span>
                        </div>

                        <div className="p-2.5 bg-[#10192e] border border-[#1f2f58] rounded-lg">
                          <div className="text-[9px] font-bold tracking-normal font-medium text-indigo-400 flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            <span>At Risk</span>
                          </div>
                          <div className="text-xl font-black text-indigo-300 font-mono mt-0.5">
                            ${(((selectedIncident.failed_transactions || 0) * 49.99)).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                          </div>
                          <span className="text-[8px] text-indigo-400 font-bold">EST. REVENUE</span>
                        </div>

                        <div className="p-2.5 bg-[#1e102e] border border-[#3b1f58] rounded-lg">
                          <div className="text-[9px] font-bold tracking-normal font-medium text-purple-400 flex items-center gap-1">
                            <Layers className="h-3 w-3" />
                            <span>Correlated</span>
                          </div>
                          <div className="text-xl font-black text-purple-300 font-mono mt-0.5">
                            {correlatedEvents.length || 1}
                          </div>
                          <span className="text-[8px] text-purple-400 font-bold">MULTI-SOURCE</span>
                        </div>
                      </div>

                      {/* Root Cause Details */}
                      {selectedIncident.root_cause && (
                        <div className="p-3 bg-[#07080d] border border-[#1f2233] text-white rounded-lg space-y-1">
                          <span className="text-[9px] font-bold tracking-normal font-medium text-cyan-400 flex items-center gap-1">
                            <Zap className="h-3 w-3" />
                            Root Cause Discovery
                          </span>
                          <p className="text-xs font-semibold leading-relaxed text-slate-100">
                            {selectedIncident.root_cause}
                          </p>
                          {selectedIncident.reasoning_summary && (
                            <p className="text-[10px] text-[#9ca3af] pt-1 border-t border-[#1a1d2b] leading-normal">
                              {selectedIncident.reasoning_summary}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Confidence & Risk Classification */}
                      <div className="flex items-center justify-between pt-1 text-[10px] text-[#8b90a0]">
                        <div className="flex items-center gap-2">
                          <Target className="h-3.5 w-3.5 text-[#1488fc]" />
                          <span>Diagnosis Confidence: <strong className="text-white font-mono">{selectedIncident.confidence || 0}%</strong></span>
                        </div>
                        {selectedIncident.risk_level && (() => {
                          const rc = getRiskColor(selectedIncident.risk_level);
                          return (
                            <span className={`px-2 py-0.5 rounded border text-[9px] font-bold tracking-normal font-medium ${rc.border} ${rc.bg} ${rc.text}`}>
                              Risk Gate: {selectedIncident.risk_level}
                            </span>
                          );
                        })()}
                      </div>
                    </div>

                    {/* Blast Radius & Affected Services */}
                    {affectedServicesList.length > 0 && (
                      <div className="p-3.5 bg-[#11131d] border border-[#1e2232] rounded-xl space-y-2">
                        <span className="text-[10px] font-bold tracking-normal font-medium text-[#a1a4a5] flex items-center gap-1">
                          <Share2 className="h-3.5 w-3.5 text-[#1488fc]" />
                          Blast Radius: Affected Services ({affectedServicesList.length})
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {affectedServicesList.map((svc: string) => (
                            <span
                              key={svc}
                              className={`px-2 py-1 text-[10px] font-mono font-bold rounded-lg border ${
                                svc.includes("database")
                                  ? "bg-red-500/15 text-red-400 border-red-500/30"
                                  : "bg-[#181b28] text-[#cbd5e1] border-[#292e42]"
                              }`}
                            >
                              {svc}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 2: TOPOLOGY GRAPH */}
                {activeTab === "topology" && (
                  <div className="space-y-3">
                    <CausalTopologyGraph
                      affectedServices={affectedServicesList}
                      rootCauseService={selectedIncident.service}
                      activeIncidentAlert={selectedIncident.alert_name}
                    />
                    <div className="p-3.5 bg-[#11131d] border border-[#1e2232] rounded-xl text-xs space-y-1.5 text-[#a1a4a5]">
                      <strong className="text-white block text-[11px] font-bold">How J.A.R.V.I.S. Solves the Challenge:</strong>
                      <p className="text-[11px] leading-relaxed text-[#a1a4a5]">
                        Instead of treating login failures in <code className="bg-[#191c2b] text-[#38bdf8] px-1 py-0.5 rounded font-mono">user-service</code>,
                        504 timeouts in <code className="bg-[#191c2b] text-[#38bdf8] px-1 py-0.5 rounded font-mono">order-service</code>, and transaction errors
                        in <code className="bg-[#191c2b] text-[#38bdf8] px-1 py-0.5 rounded font-mono">payment-service</code> as three independent problems,
                        J.A.R.V.I.S. traverses the topological call graph and shared dependency links to reveal that all three converge on
                        the shared PostgreSQL primary connection pool.
                      </p>
                    </div>
                  </div>
                )}

                {/* TAB 3: UNIFIED CHRONOLOGICAL TIMELINE */}
                {activeTab === "timeline" && (
                  <div className="p-4 bg-[#11131d] border border-[#1e2232] rounded-xl shadow-md space-y-4">
                    <div className="flex items-center justify-between border-b border-[#1b1e2c] pb-2">
                      <span className="text-xs font-bold tracking-normal font-medium text-white flex items-center gap-1.5">
                        <Clock className="h-4 w-4 text-[#1488fc]" />
                        <span>Unified Chronological Timeline</span>
                      </span>
                      <span className="text-[10px] font-mono text-[#8b90a0]">
                        {timelineData?.timeline?.length || 0} Milestones • {timelineData?.duration_seconds || 0}s MTTR
                      </span>
                    </div>

                    {!timelineData || timelineData.timeline.length === 0 ? (
                      <div className="p-6 text-center text-[#71717a] text-xs">
                        Loading unified timeline...
                      </div>
                    ) : (
                      <div className="relative border-l-2 border-[#232738] ml-3 space-y-4 pl-4 py-1">
                        {timelineData.timeline.map((item, idx) => (
                          <div key={item.id || idx} className="relative group">
                            {/* Milestone Dot */}
                            <div className="absolute -left-[23px] top-1 h-3.5 w-3.5 rounded-full border-2 border-[#11131d] bg-[#1488fc] shadow-xs" />

                            <div className="flex flex-col space-y-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-mono text-[9px] text-[#71717a]">
                                  {formatTime(item.timestamp)}
                                </span>
                                <span className={`text-[8px] font-bold px-1.5 py-0.2 rounded border font-mono ${getPhaseColor(item.phase)}`}>
                                  {item.phase}
                                </span>
                                <span className="text-[9px] font-bold text-white bg-[#191c2b] border border-[#262c3f] px-1.5 py-0.2 rounded font-mono">
                                  {item.service}
                                </span>
                                <span className="text-[8px] text-[#71717a] font-mono">
                                  ({item.source})
                                </span>
                              </div>
                              <h5 className="text-xs font-bold text-white">{item.title}</h5>
                              <p className="text-[11px] text-[#cbd5e1] leading-relaxed whitespace-pre-wrap">
                                {item.description}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 4: CORRELATED EVENTS CLUSTER */}
                {activeTab === "events" && (
                  <div className="p-4 bg-[#11131d] border border-[#1e2232] rounded-xl shadow-md space-y-3">
                    <div className="flex items-center justify-between border-b border-[#1b1e2c] pb-2">
                      <span className="text-xs font-bold tracking-normal font-medium text-white flex items-center gap-1.5">
                        <Layers className="h-4 w-4 text-[#818cf8]" />
                        <span>Correlated Multi-Source Events Cluster</span>
                      </span>
                      <span className="text-[10px] font-mono text-[#818cf8] font-bold">
                        {correlatedEvents.length} Events Correlated
                      </span>
                    </div>

                    {correlatedEvents.length === 0 ? (
                      <div className="p-6 text-center text-[#71717a] text-xs">
                        No separate events recorded. Initial alert triggered incident.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {correlatedEvents.map((ev) => (
                          <div
                            key={ev.id}
                            className="p-3 rounded-lg border border-[#1e2232] bg-[#0c0d14] space-y-1.5 text-xs"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5">
                                <span className="font-mono text-[9px] font-bold text-[#38bdf8]">{ev.id}</span>
                                <span className="px-1.5 py-0.2 rounded text-[8px] font-mono bg-purple-500/10 text-purple-300 border border-purple-500/30">
                                  {ev.source.toUpperCase()}
                                </span>
                                <span className="px-1.5 py-0.2 rounded text-[8px] font-mono bg-[#191c2b] text-white border border-[#272d42] font-bold">
                                  {ev.service}
                                </span>
                              </div>
                              <span className="font-mono text-[9px] text-[#71717a]">
                                {formatTime(ev.timestamp)}
                              </span>
                            </div>
                            <p className="text-[#cbd5e1] text-[11px] font-medium leading-relaxed">
                              {ev.message}
                            </p>
                            {ev.trace_id && (
                              <div className="text-[9px] font-mono text-[#71717a]">
                                Trace ID: <span className="text-[#93c5fd] font-semibold">{ev.trace_id}</span>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 5: AGENT LOG STREAM TERMINAL */}
                {activeTab === "terminal" && (
                  <div className="flex-1 flex flex-col space-y-2 min-h-[350px]">
                    <div ref={consoleRef} className="flex-grow bg-[#050609] border border-[#181a26] rounded-xl p-4 font-mono text-[11px] overflow-y-auto overscroll-contain flex flex-col space-y-2 shadow-inner">
                      {logs.length === 0 ? (
                        <div className="h-full flex items-center justify-center text-[#71717a] italic">
                          Idle... select an incident to stream agent logs.
                        </div>
                      ) : (
                        logs.map((log) => (
                          <div key={log.id} className="leading-relaxed whitespace-pre-wrap">
                            <span className="text-[#71717a] mr-2 text-[9px]">{formatTime(log.timestamp)}</span>
                            <span className={getLogStyle(log.level)}>{log.message}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}

                {/* TAB 6: POST-MORTEM & SRE AUDIT REPORT */}
                {activeTab === "report" && (
                  <div className="p-4 bg-[#11131d] border border-[#1e2232] rounded-xl shadow-md space-y-4">
                    <div className="flex items-center justify-between border-b border-[#1b1e2c] pb-2">
                      <span className="text-xs font-bold tracking-normal font-medium text-white flex items-center gap-1.5">
                        <FileText className="h-4 w-4 text-[#1488fc]" />
                        <span>Incident Post-Mortem & SRE Audit</span>
                      </span>
                      {selectedIncident.resolution_action && (
                        <a
                          href={`${API_URL}/api/v1/incidents/${selectedIncident.id}/report/download`}
                          download={`PostMortem-${selectedIncident.id}.md`}
                          className="flex items-center space-x-1 px-2.5 py-1 text-[10px] font-bold rounded-lg bg-[#1488fc]/15 text-[#38bdf8] hover:bg-[#1488fc]/25 border border-[#1488fc]/30 transition-all"
                        >
                          <Download className="h-3 w-3" />
                          <span>Export Markdown</span>
                        </a>
                      )}
                    </div>

                    {selectedIncident.resolution_action ? (
                      <div className="bg-[#07080d] text-[#fcfdff] p-4 rounded-xl font-mono text-[11px] leading-relaxed overflow-x-auto whitespace-pre-wrap border border-[#1c1f2e] shadow-inner max-h-[500px]">
                        {selectedIncident.resolution_action}
                      </div>
                    ) : (
                      <div className="p-8 text-center text-[#71717a] text-xs space-y-2">
                        <Clock className="h-6 w-6 text-[#71717a] mx-auto animate-pulse" />
                        <p className="font-semibold text-white">Post-Mortem in Progress</p>
                        <p className="text-[11px] text-[#71717a]">
                          The SRE Auditor compiles the unified post-mortem and business impact report upon incident resolution or governance hold.
                        </p>
                      </div>
                    )}
                  </div>
                )}

              </div>
            ) : (
              <div className="flex-grow flex flex-col items-center justify-center text-center text-[#71717a] space-y-3 p-10">
                <Terminal className="h-9 w-9 text-[#71717a] animate-pulse" />
                <div>
                  <h3 className="font-bold text-xs text-slate-400">No Incident Selected</h3>
                  <p className="text-[10px] max-w-[200px] mt-1 text-[#71717a]">Select an incident from the feed to view RCA & timelines.</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* DATA INGESTION & SCENARIO RUNNER MODAL (Task 6.5) */}
      {showIngestionModal && (
        <div className="fixed inset-0 z-50 bg-[#000000]/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#10121b] rounded-2xl shadow-2xl border border-[#232738] max-w-2xl w-full p-6 space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-[#1b1e2c] pb-3">
              <div className="flex items-center space-x-2">
                <Upload className="h-5 w-5 text-[#1488fc]" />
                <h3 className="font-heading font-black text-white text-lg">Multi-Source Data Ingestion Console</h3>
              </div>
              <button onClick={() => setShowIngestionModal(false)} className="text-[#71717a] hover:text-white cursor-pointer">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4">
              {/* Challenge Scenario Section */}
              <div className="p-4 bg-gradient-to-r from-[#11182c] to-[#151228] border border-[#232d52] rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#60a5fa] tracking-normal font-medium">J.A.R.V.I.S. Challenge Scenario</span>
                  <span className="text-[9px] bg-[#1488fc] text-white font-mono px-2 py-0.5 rounded font-bold">1-CLICK DEMO</span>
                </div>
                <p className="text-xs text-[#cbd5e1] leading-relaxed">
                  Trigger the shared database saturation outage affecting user-service (login failures), order-service (checkout latency), and payment-service (transaction errors).
                </p>
                <button
                  onClick={() => {
                    setShowIngestionModal(false);
                    runPaymentPlatformScenario();
                  }}
                  disabled={scenarioLoading}
                  className="px-4 py-2 bg-[#1488fc] hover:bg-[#0c70d4] text-white rounded-lg text-xs font-bold transition-all cursor-pointer shadow-md"
                >
                  {scenarioLoading ? "Triggering..." : "Launch Digital Payment Outage Scenario"}
                </button>
              </div>

              {/* Log File Upload */}
              <div className="p-4 bg-[#0a0b10] border border-[#1e2232] rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white tracking-normal font-medium flex items-center gap-1.5">
                    <FileText className="h-4 w-4 text-[#1488fc]" />
                    <span>Upload Log File (.log, .txt, .json, .jsonl)</span>
                  </span>
                  {selectedLogFile && (
                    <span className="text-[11px] font-mono text-[#38bdf8] bg-[#1488fc]/10 px-2 py-0.5 rounded border border-[#1488fc]/20">
                      {(selectedLogFile.size / 1024).toFixed(1)} KB
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-[#a1a4a5]">
                  Select a test log dump. Click the run button to parse timestamps, severity levels, and trace IDs, and trigger incident correlation.
                </p>

                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 pt-1">
                  <input
                    type="file"
                    accept=".log,.txt,.json,.jsonl"
                    onChange={handleFileChange}
                    disabled={uploadingLog}
                    className="block w-full text-xs text-[#a1a4a5] file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-[#1e2235] file:text-white hover:file:bg-[#282d45] cursor-pointer"
                  />
                  <button
                    type="button"
                    onClick={handleFileUpload}
                    disabled={!selectedLogFile || uploadingLog}
                    className={`px-4 py-2 rounded-lg font-bold text-xs flex items-center justify-center space-x-1.5 shrink-0 transition-colors duration-150 ${
                      !selectedLogFile || uploadingLog
                        ? "bg-[#181a26] text-[#555a6d] cursor-not-allowed border border-[#23273a]"
                        : "bg-[#1488fc] hover:bg-[#0c70d4] text-white shadow-md shadow-[#1488fc]/20 cursor-pointer"
                    }`}
                  >
                    {uploadingLog ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>Ingesting...</span>
                      </>
                    ) : (
                      <>
                        <Upload className="h-3.5 w-3.5" />
                        <span>Run Ingestion</span>
                      </>
                    )}
                  </button>
                </div>

                {/* In-Modal Feedback Alert */}
                {modalUploadStatus && (
                  <div
                    className={`p-2.5 rounded-lg text-xs font-mono border flex items-center justify-between ${
                      modalUploadStatus.type === "success"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                        : "bg-red-500/10 border-red-500/30 text-red-400"
                    }`}
                  >
                    <span>{modalUploadStatus.message}</span>
                    <button
                      type="button"
                      onClick={() => setModalUploadStatus(null)}
                      className="ml-2 hover:opacity-75 cursor-pointer font-bold"
                    >
                      ✕
                    </button>
                  </div>
                )}
              </div>

              {/* Manual API Event Emitter */}
              <form onSubmit={handleManualEventEmit} className="p-4 bg-[#0a0b10] border border-[#1e2232] rounded-xl space-y-3">
                <span className="text-xs font-bold text-white tracking-normal font-medium flex items-center gap-1.5">
                  <Send className="h-4 w-4 text-[#1488fc]" />
                  <span>Emit Live Event via API</span>
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-[10px] font-bold text-[#8b90a0]">Service</label>
                    <select
                      value={manualEventService}
                      onChange={(e) => setManualEventService(e.target.value)}
                      className="w-full text-xs p-1.5 border border-[#272b3d] rounded bg-[#141622] text-white"
                    >
                      <option value="user-service">user-service</option>
                      <option value="order-service">order-service</option>
                      <option value="payment-service">payment-service</option>
                      <option value="notification-service">notification-service</option>
                      <option value="api-gateway">api-gateway</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-[#8b90a0]">Source</label>
                    <select
                      value={manualEventSource}
                      onChange={(e) => setManualEventSource(e.target.value)}
                      className="w-full text-xs p-1.5 border border-[#272b3d] rounded bg-[#141622] text-white"
                    >
                      <option value="api">api</option>
                      <option value="logs">logs</option>
                      <option value="alertmanager">alertmanager</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-[#8b90a0]">Severity</label>
                    <select
                      value={manualEventSeverity}
                      onChange={(e) => setManualEventSeverity(e.target.value)}
                      className="w-full text-xs p-1.5 border border-[#272b3d] rounded bg-[#141622] text-white"
                    >
                      <option value="info">info</option>
                      <option value="warning">warning</option>
                      <option value="error">error</option>
                      <option value="critical">critical</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="text-[10px] font-bold text-[#8b90a0]">Message / Log Line</label>
                  <input
                    type="text"
                    value={manualEventMessage}
                    onChange={(e) => setManualEventMessage(e.target.value)}
                    className="w-full text-xs p-2 border border-[#272b3d] rounded bg-[#141622] text-white placeholder-[#52525b]"
                    placeholder="e.g. DatabaseSaturation: Auth pool checkout timed out after 3000ms"
                  />
                </div>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-[#1488fc] hover:bg-[#0c70d4] text-white rounded-lg text-xs font-bold transition-all cursor-pointer"
                >
                  Emit Event
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="bg-[#050609] border-t border-[#141622] px-8 py-5 text-center text-xs text-[#71717a] mt-auto font-sans">
        <div className="flex flex-col sm:flex-row items-center justify-between max-w-[1550px] mx-auto w-full gap-4">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-white font-medium">J.A.R.V.I.S. AI SRE Cockpit</span>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <span>Version 2.0.0</span>
            <span className="text-[#3f3f46]">|</span>
            <span>Multi-Source Incident Correlation</span>
            <span className="text-[#3f3f46]">|</span>
            <Link href="/" className="hover:text-white transition-colors">Home Page</Link>
          </div>
        </div>
      </footer>

      {/* Floating scroll-to-top button */}
      <div
        onClick={scrollToTop}
        className="fixed bottom-6 right-6 w-10 h-10 bg-[#1488fc] hover:bg-[#0c70d4] text-white rounded-xl shadow-lg transition-all duration-300 flex items-center justify-center cursor-pointer hover:shadow-xl active:scale-90 z-50 group"
      >
        <Rocket className="h-4 w-4 transform -rotate-45 group-hover:-translate-y-0.5 transition-transform" />
      </div>
    </div>
  );
}
