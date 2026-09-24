import type { BlockPlan, PipelineStep } from "@/api/types";
import { pyFileToStepTitle, sasFileToPyFile } from "@/lib/sas-python-file-map";

// Synthesize a card description from a step's BlockPlan.rationale strings —
// the same field FileBlockListPanel already treats as the primary human-readable
// label for a block (locked decision, journal/DECISIONS.md 2026-06-24). Nothing
// here is fabricated or LLM-generated at render time; it's a join/truncation of
// existing plan data.
function summarizeFileBlocks(fileBlocks: BlockPlan[]): string {
  if (fileBlocks.length === 0) return "";
  const RISK_WEIGHT: Record<BlockPlan["risk"], number> = { high: 3, medium: 2, low: 1 };
  const ranked = [...fileBlocks].sort((a, b) => RISK_WEIGHT[b.risk] - RISK_WEIGHT[a.risk]);
  const picked = ranked
    .slice(0, 3)
    .map((bp) => bp.rationale.trim())
    .filter(Boolean);
  if (picked.length === 0) {
    return `${fileBlocks.length} ${fileBlocks.length === 1 ? "block" : "blocks"} migrated`;
  }
  const joined = picked.join(" • ");
  const MAX_LEN = 170;
  return joined.length > MAX_LEN ? `${joined.slice(0, MAX_LEN - 1).trimEnd()}…` : joined;
}

// Derives the Target-mode synthetic PipelineStep array — one entry per backend
// pipeline step, but with name/description/files re-derived from the generated
// Python side (Python filenames + BlockPlan rationale) rather than the raw
// SAS-narrative fields the backend step carries. inputs/outputs/blocks mirror
// the real step's BlockPlans so box count and dataset flow always match Source's
// Pipeline view.
//
// Shared by TargetGraph.tsx (pipeline view node data) and ETLTab.tsx (the
// `allSteps` array passed to PipelineStepPanel in target mode) so producer/
// consumer lookups and displayed names stay consistent between the graph and
// the side panel — see journal/SESSIONS.md 2026-09-11 for the bug this fixes.
export function deriveTargetPipelineSteps(
  pipelineSteps: PipelineStep[],
  blockPlans: BlockPlan[],
  sasToPyMap: Map<string, string[]>,
): PipelineStep[] {
  return pipelineSteps.map((step, i) => {
    const stepBlocks = blockPlans.filter((bp) => step.blocks.includes(bp.block_id));

    const pyFilesForStep = [
      ...new Set(
        stepBlocks.flatMap(
          (bp) => sasToPyMap.get(bp.source_file) ?? [sasFileToPyFile(bp.source_file)],
        ),
      ),
    ].filter((f) => f !== "pipeline.py");

    const title =
      pyFilesForStep.length > 0
        ? pyFilesForStep.map(pyFileToStepTitle).join(" / ")
        : `Step ${i + 1}`;

    return {
      step_id: step.step_id,
      name: title,
      description: summarizeFileBlocks(stepBlocks),
      files: pyFilesForStep,
      blocks: step.blocks,
      inputs: [...new Set(stepBlocks.flatMap((bp) => bp.input_datasets))],
      outputs: [...new Set(stepBlocks.flatMap((bp) => bp.output_datasets))],
    };
  });
}
