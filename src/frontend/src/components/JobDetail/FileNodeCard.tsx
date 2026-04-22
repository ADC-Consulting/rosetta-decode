import type { FileNode } from "@/api/types";
import {
  AlertTriangle,
  Box,
  CheckCircle2,
  Cog,
  File,
  FileCode2,
  ScrollText,
  XCircle,
} from "lucide-react";
import { Handle, Position } from "reactflow";

export type FileNodeData = {
  filename: string;
  fullPath: string;
  file_type: FileNode["file_type"];
  status: FileNode["status"];
  blockCount: number;
  connectionCount: number;
  isSelected: boolean;
};

const STATUS_COLOR: Record<NonNullable<FileNode["status"]>, string> = {
  OK: "#22c55e",
  UNTRANSLATABLE: "#ef4444",
  ERROR_PRONE: "#f59e0b",
};

type PillStyle = {
  bg: string;
  color: string;
  label: string;
  icon: React.ReactElement;
};

const FILE_TYPE_PILL: Record<FileNode["file_type"], PillStyle> = {
  PROGRAM: {
    bg: "#dbeafe",
    color: "#1d4ed8",
    label: "PROGRAM",
    icon: <FileCode2 size={10} />,
  },
  MACRO: {
    bg: "#ede9fe",
    color: "#6d28d9",
    label: "MACRO",
    icon: <Box size={10} />,
  },
  AUTOEXEC: {
    bg: "#ffedd5",
    color: "#c2410c",
    label: "AUTOEXEC",
    icon: <Cog size={10} />,
  },
  LOG: {
    bg: "#f1f5f9",
    color: "#475569",
    label: "LOG",
    icon: <ScrollText size={10} />,
  },
  OTHER: {
    bg: "#f3f4f6",
    color: "#374151",
    label: "OTHER",
    icon: <File size={10} />,
  },
};

interface FileNodeCardProps {
  data: FileNodeData;
  selected: boolean;
}

export function FileNodeCard({ data }: FileNodeCardProps): React.ReactElement {
  const accentColor = data.status ? STATUS_COLOR[data.status] : "#94a3b8";
  const pill = FILE_TYPE_PILL[data.file_type];

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: accentColor,
          width: 8,
          height: 8,
          border: "2px solid #fff",
        }}
      />
      <div
        style={{
          width: 220,
          background: "#fff",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          boxShadow: data.isSelected
            ? "0 0 0 2.5px #3b82f6, 0 4px 16px rgba(59,130,246,0.18)"
            : "0 1px 5px rgba(0,0,0,0.09)",
          overflow: "hidden",
          transition: "box-shadow 0.15s ease",
          cursor: "pointer",
        }}
      >
        {/* Status accent bar */}
        <div style={{ height: 3, background: accentColor }} />

        <div style={{ padding: "8px 10px 9px" }}>
          {/* Row 1: filename + status icon */}
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: 6,
            }}
          >
            <span
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#0f172a",
                lineHeight: 1.35,
                flex: 1,
                minWidth: 0,
                overflowWrap: "break-word",
                wordBreak: "break-all",
              }}
            >
              {data.filename}
            </span>
            <span style={{ flexShrink: 0, marginTop: 1 }}>
              {data.status === "OK" && (
                <CheckCircle2 size={14} color="#22c55e" />
              )}
              {data.status === "ERROR_PRONE" && (
                <AlertTriangle size={14} color="#f59e0b" />
              )}
              {data.status === "UNTRANSLATABLE" && (
                <XCircle size={14} color="#ef4444" />
              )}
            </span>
          </div>

          {/* Row 2: file type pill + block count + connection count */}
          <div
            style={{
              marginTop: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 3,
                background: pill.bg,
                color: pill.color,
                fontSize: 9.5,
                fontWeight: 700,
                fontFamily: "ui-monospace, monospace",
                padding: "2px 6px",
                borderRadius: 4,
                letterSpacing: "0.03em",
              }}
            >
              {pill.icon}
              {pill.label}
            </span>

            <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
              <span
                style={{
                  fontSize: 10,
                  color: "#94a3b8",
                  fontFamily: "ui-monospace, monospace",
                }}
                title={`${data.blockCount} code blocks`}
              >
                {data.blockCount}B
              </span>
              {data.connectionCount > 0 && (
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: "ui-monospace, monospace",
                    fontWeight: data.connectionCount >= 4 ? 700 : 400,
                    color: data.connectionCount >= 4 ? "#f59e0b" : "#94a3b8",
                  }}
                  title={`${data.connectionCount} file connections`}
                >
                  {data.connectionCount}⇔
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: accentColor,
          width: 8,
          height: 8,
          border: "2px solid #fff",
        }}
      />
    </>
  );
}
