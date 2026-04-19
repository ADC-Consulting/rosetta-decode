import { DiffEditor } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";

interface MonacoDiffViewerProps {
  original: string;
  modified: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
}

export default function MonacoDiffViewer({
  original,
  modified,
  onChange,
  readOnly = false,
  height = "500px",
}: MonacoDiffViewerProps): React.ReactElement {
  function handleMount(editor: Monaco.editor.IStandaloneDiffEditor): void {
    editor.getModifiedEditor().onDidChangeModelContent(() => {
      onChange?.(editor.getModifiedEditor().getValue());
    });
  }

  return (
    <DiffEditor
      height={height}
      original={original}
      modified={modified}
      originalLanguage="plaintext"
      modifiedLanguage="python"
      theme="vs"
      loading={
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          Loading editor…
        </div>
      }
      options={{
        renderSideBySide: true,
        originalEditable: false,
        readOnly: readOnly,
        fontSize: 13,
        minimap: { enabled: false },
      }}
      onMount={handleMount}
    />
  );
}
