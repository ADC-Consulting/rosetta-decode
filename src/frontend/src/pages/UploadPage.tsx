import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { submitMigration } from "@/api/migrate";
import { cn } from "@/lib/utils";

export default function UploadPage() {
  const navigate = useNavigate();

  const sasInputRef = useRef<HTMLInputElement>(null);
  const refInputRef = useRef<HTMLInputElement>(null);

  const [sasFiles, setSasFiles] = useState<File[]>([]);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [sasError, setSasError] = useState<string | null>(null);
  const [refError, setRefError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => submitMigration(sasFiles, refFile ?? undefined),
    onSuccess: () => {
      navigate("/jobs");
    },
  });

  function handleSasChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? []);
    const invalid = selected.filter(
      (f) => !f.name.toLowerCase().endsWith(".sas"),
    );
    if (invalid.length > 0) {
      setSasError(
        `Invalid file(s): ${invalid.map((f) => f.name).join(", ")}. Only .sas files are allowed.`,
      );
      setSasFiles([]);
      e.target.value = "";
    } else {
      setSasError(null);
      setSasFiles(selected);
    }
  }

  function handleRefChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    if (file && !file.name.toLowerCase().endsWith(".sas7bdat")) {
      setRefError(`Invalid file: ${file.name}. Only .sas7bdat files are allowed.`);
      setRefFile(null);
      e.target.value = "";
    } else {
      setRefError(null);
      setRefFile(file);
    }
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (sasFiles.length === 0) {
      setSasError("Please select at least one .sas file.");
      return;
    }
    mutation.mutate();
  }

  const isPending = mutation.status === "pending";

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-xl font-semibold text-foreground mb-6">New Migration</h1>

      <form onSubmit={handleSubmit} noValidate className="space-y-6">
        {/* SAS files */}
        <div className="space-y-2">
          <label
            htmlFor="sas-files"
            className="block text-sm font-medium text-foreground"
          >
            SAS source files{" "}
            <span className="text-muted-foreground font-normal">(required, .sas)</span>
          </label>
          <input
            id="sas-files"
            ref={sasInputRef}
            type="file"
            accept=".sas"
            multiple
            aria-describedby={sasError ? "sas-error" : undefined}
            aria-invalid={sasError ? true : undefined}
            onChange={handleSasChange}
            className={cn(
              "block w-full text-sm text-foreground",
              "file:mr-3 file:py-1.5 file:px-3",
              "file:rounded-md file:border file:border-border",
              "file:bg-muted file:text-foreground file:text-sm file:font-medium",
              "file:cursor-pointer cursor-pointer",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              sasError && "ring-1 ring-destructive rounded-md",
            )}
          />
          {sasFiles.length > 0 && (
            <ul className="text-xs text-muted-foreground space-y-0.5 pl-1">
              {sasFiles.map((f) => (
                <li key={f.name}>{f.name}</li>
              ))}
            </ul>
          )}
          {sasError && (
            <p id="sas-error" role="alert" className="text-sm text-destructive">
              {sasError}
            </p>
          )}
        </div>

        {/* Reference dataset */}
        <div className="space-y-2">
          <label
            htmlFor="ref-dataset"
            className="block text-sm font-medium text-foreground"
          >
            Reference dataset{" "}
            <span className="text-muted-foreground font-normal">
              (optional, .sas7bdat)
            </span>
          </label>
          <input
            id="ref-dataset"
            ref={refInputRef}
            type="file"
            accept=".sas7bdat"
            aria-describedby={refError ? "ref-error" : undefined}
            aria-invalid={refError ? true : undefined}
            onChange={handleRefChange}
            className={cn(
              "block w-full text-sm text-foreground",
              "file:mr-3 file:py-1.5 file:px-3",
              "file:rounded-md file:border file:border-border",
              "file:bg-muted file:text-foreground file:text-sm file:font-medium",
              "file:cursor-pointer cursor-pointer",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              refError && "ring-1 ring-destructive rounded-md",
            )}
          />
          {refFile && (
            <p className="text-xs text-muted-foreground pl-1">{refFile.name}</p>
          )}
          {refError && (
            <p id="ref-error" role="alert" className="text-sm text-destructive">
              {refError}
            </p>
          )}
        </div>

        <Button type="submit" disabled={isPending} aria-busy={isPending}>
          {isPending ? "Submitting…" : "Migrate"}
        </Button>

        {mutation.status === "error" && (
          <p role="alert" className="text-sm text-destructive">
            {mutation.error instanceof Error
              ? mutation.error.message
              : "An unexpected error occurred."}
          </p>
        )}
      </form>
    </div>
  );
}
