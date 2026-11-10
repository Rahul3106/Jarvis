"use client";

import React from "react";
import { AlertTriangle, Info } from "lucide-react";

interface MarkdownReportRendererProps {
  content: string;
}

export default function MarkdownReportRenderer({ content }: MarkdownReportRendererProps) {
  if (!content) return null;

  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;

  const renderInline = (text: string): React.ReactNode => {
    const parts: React.ReactNode[] = [];
    const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }
      const token = match[0];
      if (token.startsWith("**") && token.endsWith("**")) {
        parts.push(
          <strong key={match.index} className="font-semibold text-white">
            {token.slice(2, -2)}
          </strong>
        );
      } else if (token.startsWith("`") && token.endsWith("`")) {
        parts.push(
          <code
            key={match.index}
            className="px-1.5 py-0.5 rounded bg-[#171a29] text-[#7dd3fc] font-mono text-[10px] border border-[#242940]"
          >
            {token.slice(1, -1)}
          </code>
        );
      }
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      i++;
      continue;
    }

    if (line === "---" || line === "***" || line === "___") {
      blocks.push(<hr key={`hr-${i}`} className="border-[#1f2233] my-4" />);
      i++;
      continue;
    }

    if (line.startsWith("# ")) {
      blocks.push(
        <h1 key={`h1-${i}`} className="text-base font-bold text-white border-b border-[#1f2233] pb-2 mt-2 mb-3 tracking-normal">
          {renderInline(line.slice(2))}
        </h1>
      );
      i++;
      continue;
    }

    if (line.startsWith("## ")) {
      blocks.push(
        <h2 key={`h2-${i}`} className="text-xs font-bold uppercase tracking-wider text-cyan-400 mt-5 mb-2 pb-1 border-b border-[#181a26]">
          {renderInline(line.slice(3))}
        </h2>
      );
      i++;
      continue;
    }

    if (line.startsWith("### ")) {
      blocks.push(
        <h3 key={`h3-${i}`} className="text-xs font-semibold text-slate-200 mt-3 mb-1.5">
          {renderInline(line.slice(4))}
        </h3>
      );
      i++;
      continue;
    }

    if (line.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }

      const firstLine = quoteLines[0] || "";
      const isWarning = firstLine.includes("[!WARNING]") || firstLine.includes("[!CAUTION]");

      const cleanLines = quoteLines.map(l =>
        l.replace(/\[!(WARNING|CAUTION|IMPORTANT|NOTE)\]/g, "").trim()
      ).filter(Boolean);

      blocks.push(
        <div
          key={`quote-${i}`}
          className={`p-3 rounded-lg border my-3 space-y-1 text-xs ${
            isWarning
              ? "bg-amber-950/30 border-amber-500/50 text-amber-200"
              : "bg-blue-950/30 border-blue-500/50 text-blue-200"
          }`}
        >
          <div className="flex items-center gap-1.5 font-bold text-[11px]">
            {isWarning ? (
              <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
            ) : (
              <Info className="h-3.5 w-3.5 text-blue-400 shrink-0" />
            )}
            <span>{isWarning ? "Safety Governance Alert" : "SRE Auditor Note"}</span>
          </div>
          {cleanLines.map((cl, idx) => (
            <p key={idx} className="leading-relaxed">
              {renderInline(cl)}
            </p>
          ))}
        </div>
      );
      continue;
    }

    if (line.startsWith("|") && line.endsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        tableLines.push(lines[i].trim());
        i++;
      }

      if (tableLines.length >= 2) {
        const headerCells = tableLines[0]
          .split("|")
          .slice(1, -1)
          .map(c => c.trim());
        
        const rowLines = tableLines.slice(2);

        blocks.push(
          <div key={`table-${i}`} className="overflow-x-auto my-3 rounded-lg border border-[#1f2233]">
            <table className="w-full text-left text-[11px] font-sans border-collapse">
              <thead className="bg-[#121522] text-slate-300 font-semibold border-b border-[#1f2233]">
                <tr>
                  {headerCells.map((h, idx) => (
                    <th key={idx} className="px-3 py-2 border-r border-[#1f2233] last:border-r-0 whitespace-nowrap text-[10px] uppercase tracking-wider text-slate-400">
                      {renderInline(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#181a28] bg-[#090b12]">
                {rowLines.map((rl, rIdx) => {
                  const cells = rl
                    .split("|")
                    .slice(1, -1)
                    .map(c => c.trim());
                  return (
                    <tr key={rIdx} className="hover:bg-[#141726]/60 transition-colors">
                      {cells.map((cell, cIdx) => (
                        <td
                          key={cIdx}
                          className="px-3 py-1.5 border-r border-[#181a28] last:border-r-0 text-slate-300 leading-snug"
                        >
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
        continue;
      }
    }

    if (line.startsWith("* ") || line.startsWith("- ")) {
      const listItems: string[] = [];
      while (i < lines.length && (lines[i].trim().startsWith("* ") || lines[i].trim().startsWith("- "))) {
        listItems.push(lines[i].trim().slice(2));
        i++;
      }

      blocks.push(
        <ul key={`ul-${i}`} className="list-disc list-inside space-y-1 text-slate-300 text-xs my-2 ml-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      const numItems: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        numItems.push(lines[i].trim().replace(/^\d+\.\s/, ""));
        i++;
      }

      blocks.push(
        <ol key={`ol-${i}`} className="list-decimal list-inside space-y-1 text-slate-300 text-xs my-2 ml-1">
          {numItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    blocks.push(
      <p key={`p-${i}`} className="text-slate-300 text-xs leading-relaxed my-1.5">
        {renderInline(line)}
      </p>
    );
    i++;
  }

  return <div className="space-y-1 text-slate-300 font-sans leading-relaxed">{blocks}</div>;
}
