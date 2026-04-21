import type { FileNode } from "@/api/types";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Handle, Position } from "reactflow";

export type FileNodeData = {
  filename: string;
  fullPath: string;
  file_type: FileNode["file_type"];
  status: FileNode["status"];
  blockCount: number;
  isSelected: boolean;
};

const STATUS_BORDER: Record<NonNullable<FileNode["status"]>, string> = {
  OK: "#22c55e",
  UNTRANSLATABLE: "#ef4444",
  ERROR_PRONE: "#f59e0b",
};

const FILE_TYPE_STYLE: Record<FileNode["file_type"], { bg: string; text: string }> = {
  PROGRAM: { bg: "bg-blue-100", text: "text-blue-700" },
  MACRO: { bg: "bg-purple-100", text: "text-purple-700" },
  AUTOEXEC: { bg: "bg-orange-100", text: "text-orange-700" },
  LOG: { bg: "bg-slate-100", text: "text-slate-600" },
  OTHER: { bg: "bg-gray-100", text: "text-gray-600" },
};

interface FileNodeCardProps {
  data: FileNodeData;
  selected: boolean;
}

export function FileNodeCard({ data }: FileNodeCardProps): React.ReactElement {
  const borderColor = data.status ? STATUS_BORDER[data.status] : "#94a3b8";
  const typeStyle = FILE_TYPE_STYLE[data.file_type];

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ background: "#94a3b8" }} />
      <div
        className={`w-[220px] h-[90px] rounded-lg px-3 py-2 bg-white shadow-sm cursor-pointer border-2${
          data.isSelected ? " ring-2 ring-blue-500 ring-offset-1" : ""
        }`}
        style={{ borderColor }}
      >
        {/* Row 1: filename */}
        <div className="text-sm font-semibold text-slate-800 truncate">{data.filename}</div>

        {/* Row 2: file_type badge + status icon */}
        <div className="flex justify-between items-center mt-1">
          <span
            className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${typeStyle.bg} ${typeStyle.text}`}
          >
            {data.file_type}
          </span>
          {data.status === "OK" && <CheckCircle2 size={14} className="text-green-500 shrink-0" />}
          {data.status === "ERROR_PRONE" && (
            <AlertTriangle size={14} className="text-amber-500 shrink-0" />
          )}
          {data.status === "UNTRANSLATABLE" && (
            <XCircle size={14} className="text-red-500 shrink-0" />
          )}
        </div>

        {/* Row 3: block count */}
        <div className="text-xs text-slate-400 font-mono mt-1">{data.blockCount} blocks</div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "#94a3b8" }} />
    </>
  );
}
