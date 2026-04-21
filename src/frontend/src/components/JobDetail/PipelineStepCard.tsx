import { Handle, Position } from "reactflow";

export type PipelineStepData = {
  stepNumber: number;
  name: string;
  description: string;
  inputCount: number;
  outputCount: number;
};

interface PipelineStepCardProps {
  data: PipelineStepData;
}

export function PipelineStepCard({ data }: PipelineStepCardProps): React.ReactElement {
  const stepLabel = String(data.stepNumber).padStart(2, "0");

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ background: "#94a3b8" }} />
      <div className="w-[240px] h-[80px] rounded-lg px-3 py-2 bg-white shadow-sm border-2 border-indigo-300">
        {/* Row 1: step badge + name */}
        <div className="flex gap-2 items-center">
          <span className="font-mono text-xs bg-indigo-100 text-indigo-700 rounded px-1 shrink-0">
            [{stepLabel}]
          </span>
          <span className="text-sm font-semibold text-slate-800 truncate">{data.name}</span>
        </div>

        {/* Row 2: in/out counts */}
        <div className="text-xs text-slate-400 mt-1">
          ↳ {data.inputCount} in → {data.outputCount} out
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "#94a3b8" }} />
    </>
  );
}
