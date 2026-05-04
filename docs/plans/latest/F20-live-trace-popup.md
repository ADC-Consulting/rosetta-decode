# F20 — Live Trace Popup + Rich Execution Results

**Status:** in-progress — Stream A complete; recon grouping + retry loop + session cache fixed (session 3); Stream B pending

## Remaining Work (2026-05-03 session 3)

### B — Stream B (ExecutionOutputPanel + Trust tab)
As per original plan sections B1 and B2 below.

### Open bug
- `tx_fx_cat` NameError on attempt 1 still seen — session cache `/tmp` fix deployed but not yet confirmed working after docker rebuild; root cause: Spark save snippet crashes if the prior block's code itself raises before saving (the `_customer_id_type` line is LLM-generated introspection code that shouldn't be there — an LLM prompt artifact, not a cache issue)

## Completed This Session (2026-05-03 session 2)

### C — LiveTraceDialog UX Overhaul ✓
- [x] Block colour states: grey=running, red=error, amber=no-recon, green=pass, red=fail
- [x] `pipeline:full` summary banner with coloured border + collapsible recon checks
- [x] Human-friendly check labels (Schema Parity, Row Count, Aggregate Parity)
- [x] Auto-expand on recon arrival; user toggle preserved (null→hasRecon→userToggled)
- [x] No coloured left border on block header button; no inner rail in collapsible
- [x] Shimmer keyframe fixed (duplicate removed from index.css)

### Per-block recon with DataFrame session cache ✓
- [x] `src/executor/runner.py` — `session_dir` param: Parquet load snippet prepended, save snippet appended, `_ROSETTA_SESSION_DIR` env var
- [x] `src/executor/main.py` — `session_dir` on `ExecuteRequest`
- [x] `src/worker/validation/reconciliation.py` — `session_dir` threaded through `_post_execute` and `run`
- [x] `src/worker/engine/block_executor.py` — `session_dir` param forwarded
- [x] `src/worker/main.py` — per-block recon via session cache; `_build_recon_groups` fallback removed (per-block only for specifically-matched data files); `pipeline:full` final run with SSE trace events; cache cleanup
- [x] `src/executor/recon.py` — both ref and actual DataFrames normalized to lowercase columns before all checks
- [x] `src/worker/engine/agents/shared.py` — Rule 2 strengthened: mandatory lowercase after every file read, concrete `toDF` example

## Context

Two UX gaps:
1. **During migration**: the jobs table gives no visibility into what the worker/LLM is doing. Users can't follow progress, see which block is translating, or stop a runaway job.
2. **After running code in the editor**: the Output/Result/Recon tabs show raw data. There's no per-file comparison, stderr is unsplit, and the recon display is dense.

The image shared shows the desired layout: a large popup with flushed live text, structured per-block progress, and a stop button.

---

## Stream A — Live Trace Popup (jobs table → running/queued job)

### A1: DB migration ✓
**New file:** `alembic/versions/016_add_job_traces_cancel.py`
**Modified:** `src/backend/db/models.py`

- Add `cancellation_requested: Mapped[bool]` column to `Job` (default `False`)
- Add new model `JobTrace`:
  ```python
  class JobTrace(Base):
      __tablename__ = "job_traces"
      id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
      job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
      event_type: Mapped[str] = mapped_column(String(32))   # block_start|block_done|recon_result|job_done|error
      payload: Mapped[dict] = mapped_column(JSON)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  ```
  Index on `(job_id, id)`. The `id` PK acts as the monotonic seq.

### A2: Worker — TraceEmitter + cancel check
**New file:** `src/worker/engine/trace.py`

```python
class TraceEmitter:
    def __init__(self, job_id: str, session_factory) -> None: ...
    async def emit(self, event_type: str, payload: dict) -> None:
        """Insert JobTrace row. Never raises."""
```

**Modified:** `src/worker/main.py`

- `JobOrchestrator.__init__`: instantiate `TraceEmitter(job.id, session_factory)`
- `_translate_blocks` inner loop — after the existing `logger.info("[F19] ...")` line:
  ```python
  await self._tracer.emit("block_start", {"block_id": block_id, "agent": type(translator).__name__, "attempt": attempt})
  ```
  After recon result is known:
  ```python
  await self._tracer.emit("block_done", {"block_id": block_id, "attempt": attempt, "status": ..., "elapsed_ms": ...})
  await self._tracer.emit("recon_result", {"block_id": block_id, "checks": checks, "all_passed": ...})
  ```
  After each block, check for cancellation:
  ```python
  await session.refresh(job)
  if job.cancellation_requested:
      raise JobCancelledException(f"Job {job.id} cancelled")
  ```
- `JobOrchestrator.run()`: catch `JobCancelledException`, set `job.status = "cancelled"`, emit `job_done`, commit.
- On normal completion: emit `job_done` with `final_status`.

**New exception:** `class JobCancelledException(Exception): ...` (in `src/worker/main.py` or `src/worker/engine/trace.py`)

### A3: Backend — POST /jobs/{id}/cancel
**Modified:** `src/backend/api/routes/jobs.py`

```python
@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: UUID, session: AsyncSession = Depends(...)):
    job = await session.get(Job, str(job_id))
    if not job: raise HTTPException(404)
    if job.status not in ("queued", "running"):
        raise HTTPException(409, detail=f"Job is not cancellable: {job.status}")
    prev = job.status
    if job.status == "queued":
        job.status = "cancelled"
    else:  # running
        job.cancellation_requested = True
    await session.commit()
    return {"job_id": str(job_id), "previous_status": prev, "cancelled": True}
```

### A4: Backend — GET /jobs/{id}/trace/stream
**Modified:** `src/backend/api/routes/jobs.py`

SSE endpoint. Follows the same pattern as `src/backend/api/routes/explain.py:143-173`.

```python
@router.get("/jobs/{job_id}/trace/stream")
async def stream_job_trace(job_id: UUID, since_seq: int = 0):
    async def generate():
        last_id = since_seq
        while True:
            async with AsyncSession(engine) as session:
                rows = await session.execute(
                    select(JobTrace)
                    .where(JobTrace.job_id == str(job_id), JobTrace.id > last_id)
                    .order_by(JobTrace.id)
                )
                for row in rows.scalars():
                    payload = {"event_type": row.event_type, **row.payload}
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_id = row.id
                    if row.event_type == "job_done":
                        return
            # check if job is in terminal state with no more traces
            job = await session.get(Job, str(job_id))
            if job and job.status not in ("queued", "running"):
                return
            await asyncio.sleep(0.5)
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**SSE event shapes** (all fields):
```
block_start:   { event_type, block_id, agent, attempt, ts }
block_done:    { event_type, block_id, attempt, status:"pass"|"fail"|"error", elapsed_ms, ts }
recon_result:  { event_type, block_id, checks:[{name,status,detail}], all_passed, ts }
job_done:      { event_type, job_id, final_status, ts }
error:         { event_type, message, ts }
```

### A5: Frontend types + API
**Modified:** `src/frontend/src/api/types.ts` — add `TraceEvent` union type and sub-interfaces (see shapes above).

**Modified:** `src/frontend/src/api/jobs.ts`
```typescript
export function openTraceStream(jobId: string, sinceSeq = 0): EventSource {
  return new EventSource(`/api/jobs/${jobId}/trace/stream?since_seq=${sinceSeq}`);
}
export async function cancelJob(jobId: string): Promise<void> { ... }
```

### A6: Frontend — LiveTraceDialog component
**New file:** `src/frontend/src/components/LiveTraceDialog.tsx`

Props:
```typescript
interface LiveTraceDialogProps {
  jobId: string;
  jobName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onJobDone?: (finalStatus: string) => void;
}
```

Layout (matches image): large `DialogContent` — `max-w-3xl w-[95vw] h-[80vh] flex flex-col`
- **Header**: job name + live status chip (Connecting / Streaming / Done)
- **Body** (`flex-1 overflow-y-auto font-mono text-sm`): scrollable event list. Each event type gets its own row style:
  - `block_start` → `▶ DataStepAgent — file.sas:12 (attempt 1/3)` with a spinning indicator
  - `block_done pass` → green `✓ file.sas:12 — 1.2s`
  - `block_done fail` → amber `✗ file.sas:12 — failed (attempt 1)`
  - `recon_result` → indented list of check badges (schema_parity ✓, row_count ✗ ref=100 actual=98)
  - `job_done` → banner with final status
  - `error` → red text
- **Footer**: Stop button (red, disabled after cancel/done) + elapsed timer + close button
- Auto-scroll: `useEffect` on events length, `scrollIntoView` on last item ref
- Uses `react-markdown` for any `message` fields that contain markdown (error events)
- SSE lifecycle: `useEffect` opens `EventSource` when `open=true`, closes on unmount or `open=false`. Tracks `lastSeq` for reconnect.

### A7: Frontend — trace button in JobsPage
**Modified:** `src/frontend/src/pages/JobsPage.tsx`

- Add `traceJobId: string | null` state
- In job row action cell: if `status === "queued" || status === "running"`, render an `Activity` icon button that calls `setTraceJobId(job.job_id)` and stops row-click propagation
- Render `<LiveTraceDialog open={!!traceJobId} jobId={traceJobId ?? ""} ... onJobDone={() => queryClient.invalidateQueries(["jobs"])} />` once at page bottom

---

## Stream B — Rich Execution Results (EditorTab)

All frontend-only. No backend changes.

### B1: ExecutionOutputPanel improvements
**Modified:** `src/frontend/src/components/JobDetail/EditorTab.tsx`

- **Output tab elapsed**: change tab label to `Output (1.2s)` when result is set — `result ? \`Output (${(result.elapsed_ms/1000).toFixed(1)}s)\` : "Output"`
- **stderr split**: parse stderr lines — lines containing `WARNING` → amber `<pre>`; lines containing `ERROR` or `Traceback` → red `<pre>`; split at render time, no backend change
- **Recon tab cards**: replace flat `divide-y` list with styled cards — each check: colored left border (green/red), larger name label (remove `w-36` fixed width), detail in `<pre className="text-xs mt-1 whitespace-pre-wrap">`, pass/fail badge with color

### B2: Trust tab in bottom panel
**Modified:** `src/frontend/src/components/JobDetail/EditorTab.tsx`

- Add `"trust"` to `BottomTab` type
- Add `trustReport?: TrustReportResponse` prop to `EditorTab` (type already exists in `types.ts`)
- New "Trust" tab in `BottomPanel` renders `trustReport.blocks` filtered by `source_file === effectiveSasKey` (current SAS file selected in left panel) — shows: block name, strategy, confidence badge, recon status badge, detail
- Falls back to "Select a SAS file to see block trust details" when no file selected

**Modified:** `src/frontend/src/pages/JobDetailPage.tsx`
- Pass `trustReport={trustReportData}` to `EditorTab` (the trust report query is already run in `JobDetailPage`)

---

## Sequencing

```
A1 (migration) → A2, A3, A4 in parallel → A5 → A6 → A7
B1, B2: fully independent, can start immediately
```

A1 must land before A2-A4 can run end-to-end. A5-A7 can be stubbed/built in parallel with A2-A4 and wired once the backend is ready.

---

## Files summary

| File | Change |
|---|---|
| `alembic/versions/XXXX_add_job_traces_cancel.py` | **NEW** — migration |
| `src/backend/db/models.py` | Add `JobTrace` model + `cancellation_requested` on `Job` |
| `src/backend/api/routes/jobs.py` | Add `POST /cancel` + `GET /trace/stream` |
| `src/worker/engine/trace.py` | **NEW** — `TraceEmitter` |
| `src/worker/main.py` | Wire `TraceEmitter`, cancel check, `JobCancelledException` |
| `src/frontend/src/api/types.ts` | Add `TraceEvent*` types |
| `src/frontend/src/api/jobs.ts` | Add `openTraceStream`, `cancelJob` |
| `src/frontend/src/components/LiveTraceDialog.tsx` | **NEW** |
| `src/frontend/src/pages/JobsPage.tsx` | Trace button + dialog mount |
| `src/frontend/src/components/JobDetail/EditorTab.tsx` | B1+B2 enrichments |
| `src/frontend/src/pages/JobDetailPage.tsx` | Pass `trustReport` to `EditorTab` |

## Verification

1. `make test` green
2. `make docker-build` + `docker compose up`
3. Submit a job → jobs table shows activity button → click it → dialog opens, events flush live
4. Click Stop mid-run → worker cancels after current block → job status → `cancelled`
5. Wait for job completion → `job_done` event → dialog shows final status → button changes to Close
6. Open a done job → Editor tab → Run ▶ → Output tab shows elapsed in label, stderr split, Recon tab shows cards → Trust tab shows per-block confidence for selected SAS file
