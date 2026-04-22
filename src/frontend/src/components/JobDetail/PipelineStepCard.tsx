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

export function PipelineStepCard({
  data,
}: PipelineStepCardProps): React.ReactElement {
  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: "#6366f1",
          width: 8,
          height: 8,
          border: "2px solid #fff",
        }}
      />
      <div
        style={{
          width: 240,
          background: "#fff",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          boxShadow: "0 1px 5px rgba(0,0,0,0.09)",
          overflow: "hidden",
        }}
      >
        {/* Indigo gradient accent bar */}
        <div
          style={{
            height: 3,
            background: "linear-gradient(90deg, #6366f1 0%, #a5b4fc 100%)",
          }}
        />

        <div
          style={{
            padding: "8px 10px 9px",
            display: "flex",
            gap: 10,
            alignItems: "flex-start",
          }}
        >
          {/* Step number circle */}
          <div
            style={{
              flexShrink: 0,
              width: 28,
              height: 28,
              borderRadius: "50%",
              background: "#eef2ff",
              border: "1.5px solid #a5b4fc",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              fontWeight: 700,
              fontFamily: "ui-monospace, monospace",
              color: "#4f46e5",
            }}
          >
            {data.stepNumber}
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#0f172a",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {data.name}
            </div>
            {data.description && (
              <div
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  marginTop: 2,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {data.description}
              </div>
            )}
            <div
              style={{
                marginTop: 5,
                display: "flex",
                gap: 8,
                fontSize: 10,
                color: "#94a3b8",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              <span>↑ {data.inputCount} in</span>
              <span>↓ {data.outputCount} out</span>
            </div>
          </div>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: "#6366f1",
          width: 8,
          height: 8,
          border: "2px solid #fff",
        }}
      />
    </>
  );
}
