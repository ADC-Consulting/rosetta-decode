import type { JobLineageResponse, LineageEdge, PipelineStep } from "../api/types";

export function mergePipelineLineages(
  responses: Array<{ jobId: string; lineage: JobLineageResponse }>,
): JobLineageResponse {
  const nodes = responses.flatMap(({ jobId, lineage }) =>
    (lineage.nodes ?? []).map((n) => ({ ...n, id: `${jobId}_${n.id}` })),
  );

  const edges = responses.flatMap(({ jobId, lineage }) =>
    (lineage.edges ?? []).map((e) => ({
      ...e,
      source: `${jobId}_${e.source}`,
      target: `${jobId}_${e.target}`,
    })),
  );

  const pipelineSteps = responses.flatMap(({ jobId, lineage }) =>
    (lineage.pipeline_steps ?? []).map((s) => ({
      ...s,
      step_id: `${jobId}_${s.step_id}`,
    })),
  );

  const fileNodes = responses.flatMap(({ jobId, lineage }) =>
    (lineage.file_nodes ?? []).map((fn) => ({
      ...fn,
      filename: `${jobId}_${fn.filename}`,
    })),
  );

  const fileEdges = responses.flatMap(({ jobId, lineage }) =>
    (lineage.file_edges ?? []).map((fe) => ({
      ...fe,
      source_file: `${jobId}_${fe.source_file}`,
      target_file: `${jobId}_${fe.target_file}`,
    })),
  );

  const syntheticEdges = buildCrossMigrationEdges(
    responses.map(({ jobId, lineage }) => ({
      jobId,
      steps: lineage.pipeline_steps ?? [],
    })),
  );

  return {
    job_id: "global",
    nodes,
    edges: [...edges, ...syntheticEdges],
    pipeline_steps: pipelineSteps,
    file_nodes: fileNodes,
    file_edges: fileEdges,
  };
}

function buildCrossMigrationEdges(
  migrations: Array<{ jobId: string; steps: PipelineStep[] }>,
): LineageEdge[] {
  const result: LineageEdge[] = [];

  for (let i = 0; i < migrations.length; i++) {
    for (let j = 0; j < migrations.length; j++) {
      if (i === j) continue;
      const migA = migrations[i];
      const migB = migrations[j];

      for (const stepA of migA.steps) {
        for (const stepB of migB.steps) {
          for (const output of stepA.outputs) {
            if (stepB.inputs.includes(output)) {
              result.push({
                source: `${migA.jobId}_${stepA.step_id}`,
                target: `${migB.jobId}_${stepB.step_id}`,
                dataset: output,
                inferred: true,
              });
            }
          }
        }
      }
    }
  }

  return result;
}
