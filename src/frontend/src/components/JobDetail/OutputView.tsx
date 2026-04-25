import { getAttachmentUrl } from "@/api/jobs";
import type { AttachmentInfo } from "@/api/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Download } from "lucide-react";
import { useEffect, useState } from "react";

interface OutputViewProps {
  jobId: string;
  attachments: AttachmentInfo[];
}

/** Minimal RFC-4180–compatible CSV parser — no external dependency required. */
function parseCsv(raw: string): { headers: string[]; rows: string[][] } {
  const lines = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const parse = (line: string): string[] => {
    const result: string[] = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuotes && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch === "," && !inQuotes) {
        result.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    result.push(cur);
    return result;
  };

  const nonEmpty = lines.filter((l) => l.trim() !== "");
  if (nonEmpty.length === 0) return { headers: [], rows: [] };
  const [headerLine, ...dataLines] = nonEmpty;
  return {
    headers: parse(headerLine),
    rows: dataLines.map(parse),
  };
}

const PREVIEW_EXTENSIONS = new Set([".csv", ".tsv", ".txt"]);
const MAX_PREVIEW_ROWS = 500;

export default function OutputView({ jobId, attachments }: OutputViewProps): React.ReactElement {
  const [selectedKey, setSelectedKey] = useState<string>(attachments[0]?.path_key ?? "");
  const [csvData, setCsvData] = useState<{ headers: string[]; rows: string[][] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedAttachment = attachments.find((a) => a.path_key === selectedKey) ?? null;
  const canPreview = selectedAttachment
    ? PREVIEW_EXTENSIONS.has(selectedAttachment.extension.toLowerCase())
    : false;

  useEffect(() => {
    if (attachments.length > 0 && !selectedKey) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedKey(attachments[0].path_key);
    }
  }, [attachments, selectedKey]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCsvData(null);
    setError(null);
    if (!selectedKey || !canPreview) return;
    setLoading(true);
    fetch(getAttachmentUrl(jobId, selectedKey))
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load file (${res.status})`);
        return res.text();
      })
      .then((text) => setCsvData(parseCsv(text)))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [jobId, selectedKey, canPreview]);

  if (attachments.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground px-6 text-center">
        No output files uploaded. Include .csv or .xlsx files in your zip to view them here.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {attachments.length > 1 && (
        <div className="flex gap-1 px-3 py-2 border-b border-border shrink-0 flex-wrap">
          {attachments.map((a) => (
            <button
              key={a.path_key}
              onClick={() => setSelectedKey(a.path_key)}
              className={cn(
                "px-2.5 py-1 text-xs rounded border transition-colors cursor-pointer",
                selectedKey === a.path_key
                  ? "border-primary bg-primary/10 text-primary font-medium"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30",
              )}
            >
              {a.filename}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
          Loading…
        </div>
      )}

      {error && (
        <div className="flex items-center justify-center h-32 text-sm text-red-600 px-4 text-center">
          {error}
        </div>
      )}

      {!loading && !error && !canPreview && selectedAttachment && (
        <div className="flex flex-col items-center justify-center gap-3 h-48 text-sm text-muted-foreground">
          <p>Preview not available for {selectedAttachment.extension.toUpperCase()} files.</p>
          <a
            href={getAttachmentUrl(jobId, selectedKey)}
            download={selectedAttachment.filename}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded
              hover:bg-muted/50 text-foreground transition-colors"
          >
            <Download size={13} />
            Download {selectedAttachment.filename}
          </a>
        </div>
      )}

      {!loading && !error && canPreview && csvData && (
        <div className="flex-1 min-h-0 overflow-auto" style={{ maxHeight: "60vh" }}>
          {csvData.headers.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">File is empty or could not be parsed.</p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    {csvData.headers.map((h, i) => (
                      <TableHead key={i} className="whitespace-nowrap text-xs font-semibold">
                        {h}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {csvData.rows.slice(0, MAX_PREVIEW_ROWS).map((row, ri) => (
                    <TableRow key={ri}>
                      {row.map((cell, ci) => (
                        <TableCell key={ci} className="text-xs font-mono whitespace-nowrap">
                          {cell}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {csvData.rows.length > MAX_PREVIEW_ROWS && (
                <p className="px-3 py-2 text-xs text-muted-foreground border-t border-border">
                  Showing first {MAX_PREVIEW_ROWS} of {csvData.rows.length} rows.{" "}
                  <a
                    href={getAttachmentUrl(jobId, selectedKey)}
                    download={selectedAttachment?.filename}
                    className="underline hover:text-foreground"
                  >
                    Download full file
                  </a>
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
