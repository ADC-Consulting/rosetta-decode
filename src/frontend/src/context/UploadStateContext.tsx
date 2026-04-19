import { createContext, useContext, useRef, useState } from "react";
import JSZip from "jszip";
import type { MigrateResponse } from "@/api/types";

export interface ZipEntry {
  file: File;
  entries: string[];
  expanded: boolean;
  excluded: Set<string>;
  loading: boolean;
}

export type UploadPhase = "staging" | "submitted";

export interface UploadState {
  phase: UploadPhase;
  files: File[];
  zipEntries: Map<string, ZipEntry>;
  manifest: MigrateResponse | null;
  dragOver: boolean;
  migrationName: string;
  setMigrationName: (v: string) => void;
  setDragOver: (v: boolean) => void;
  applyFiles: (incoming: File[]) => void;
  removeFile: (name: string) => void;
  toggleZipExpanded: (zipName: string) => void;
  excludeZipEntry: (zipName: string, entryPath: string) => void;
  setManifest: (m: MigrateResponse) => void;
  setPhase: (p: UploadPhase) => void;
  /** Clears everything — only call when user explicitly wants a fresh start */
  reset: () => void;
  /** Go back to staging form without clearing the submitted result */
  newMigration: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

const Ctx = createContext<UploadState | null>(null);

function isHidden(entryPath: string): boolean {
  const parts = entryPath.split("/");
  return parts.some((p) => p.startsWith("__MACOSX") || p.startsWith("."));
}

export function UploadStateProvider({ children }: { children: React.ReactNode }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<UploadPhase>("staging");
  const [files, setFiles] = useState<File[]>([]);
  const [zipEntries, setZipEntries] = useState<Map<string, ZipEntry>>(new Map());
  const [manifest, setManifestState] = useState<MigrateResponse | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [migrationName, setMigrationName] = useState<string>("");

  async function parseZip(file: File): Promise<void> {
    setZipEntries((prev) => {
      const next = new Map(prev);
      next.set(file.name, {
        file,
        entries: [],
        expanded: true,
        excluded: new Set(),
        loading: true,
      });
      return next;
    });

    try {
      const zip = await JSZip.loadAsync(file);
      const names: string[] = [];
      zip.forEach((relativePath, zipObj) => {
        if (!zipObj.dir && !isHidden(relativePath)) names.push(relativePath);
      });
      setZipEntries((prev) => {
        const next = new Map(prev);
        const existing = next.get(file.name);
        if (existing) next.set(file.name, { ...existing, entries: names, loading: false });
        return next;
      });
    } catch {
      setZipEntries((prev) => {
        const next = new Map(prev);
        const existing = next.get(file.name);
        if (existing) next.set(file.name, { ...existing, loading: false });
        return next;
      });
    }
  }

  function applyFiles(incoming: File[]) {
    const newZips: File[] = [];
    setFiles((prev) => {
      const existing = new Map(prev.map((f) => [f.name, f]));
      for (const f of incoming) {
        existing.set(f.name, f);
        if (f.name.toLowerCase().endsWith(".zip")) newZips.push(f);
      }
      return Array.from(existing.values());
    });
    // parse after state update to avoid stale closure — use setTimeout(0) to yield
    setTimeout(() => {
      for (const z of newZips) void parseZip(z);
    }, 0);
  }

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((f) => f.name !== name));
    setZipEntries((prev) => {
      const next = new Map(prev);
      next.delete(name);
      return next;
    });
  }

  function toggleZipExpanded(zipName: string) {
    setZipEntries((prev) => {
      const next = new Map(prev);
      const entry = next.get(zipName);
      if (entry) next.set(zipName, { ...entry, expanded: !entry.expanded });
      return next;
    });
  }

  function excludeZipEntry(zipName: string, entryPath: string) {
    setZipEntries((prev) => {
      const next = new Map(prev);
      const entry = next.get(zipName);
      if (entry) {
        const excluded = new Set(entry.excluded);
        excluded.add(entryPath);
        next.set(zipName, { ...entry, excluded });
      }
      return next;
    });
  }

  function setManifest(m: MigrateResponse) {
    setManifestState(m);
  }

  function reset() {
    setPhase("staging");
    setFiles([]);
    setZipEntries(new Map());
    setManifestState(null);
    setMigrationName("");
  }

  function newMigration() {
    // Go back to staging but keep manifest so the result card is still visible
    // when the user returns to /upload.  Files are cleared so the form is fresh.
    setPhase("staging");
    setFiles([]);
    setZipEntries(new Map());
    setMigrationName("");
  }

  return (
    <Ctx.Provider
      value={{
        phase, setPhase,
        files, zipEntries,
        manifest,
        dragOver, setDragOver,
        migrationName, setMigrationName,
        applyFiles, removeFile,
        toggleZipExpanded, excludeZipEntry,
        setManifest,
        reset,
        newMigration,
        inputRef,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useUploadState(): UploadState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useUploadState must be used within UploadStateProvider");
  return ctx;
}
