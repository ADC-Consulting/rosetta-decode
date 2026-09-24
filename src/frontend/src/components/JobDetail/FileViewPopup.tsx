import { Suspense, lazy } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useBrandManifestContainer } from "@/lib/useBrandManifestContainer";
import { registerSasLanguage } from "./registerSasLanguage";

const Editor = lazy(() => import("@monaco-editor/react"));

interface FileViewPopupProps {
  filename: string;
  language: "sas" | "python";
  content: string;
  onClose: () => void;
}

export default function FileViewPopup({
  filename,
  language,
  content,
  onClose,
}: FileViewPopupProps): React.ReactElement {
  const basename = filename.split("/").pop() ?? filename;
  const lineCount = content.split("\n").length;
  const container = useBrandManifestContainer();

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        container={container}
        className="flex flex-col gap-0 p-0 overflow-hidden"
        style={{ width: "80vw", maxWidth: "80vw", height: "80vh", maxHeight: "80vh" }}
        aria-label={`File: ${basename}`}
      >
        <DialogHeader className="flex flex-row items-center gap-3 px-4 py-3 border-b border-border shrink-0">
          <DialogTitle className="font-mono text-sm font-semibold truncate">
            {basename}
          </DialogTitle>
          <span className="text-xs text-muted-foreground shrink-0">
            {lineCount} lines
          </span>
        </DialogHeader>

        <div className="flex-1 min-h-0">
          {content ? (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Loading…
                </div>
              }
            >
              <Editor
                key={`file-view-${filename}`}
                height="100%"
                defaultValue={content}
                language={language}
                theme={language === "sas" ? "sas-light" : "vs"}
                beforeMount={language === "sas" ? registerSasLanguage : undefined}
                loading={
                  <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                    Loading…
                  </div>
                }
                options={{
                  readOnly: true,
                  fontSize: 13,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  lineNumbers: "on",
                  wordWrap: "off",
                }}
              />
            </Suspense>
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              File content not available.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
