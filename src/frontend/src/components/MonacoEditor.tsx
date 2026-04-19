import { Editor } from "@monaco-editor/react";

interface MonacoEditorProps {
  value: string;
  language?: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
}

export default function MonacoEditor({
  value,
  language = "python",
  onChange,
  readOnly = false,
  height = "500px",
}: MonacoEditorProps): React.ReactElement {
  return (
    <Editor
      height={height}
      value={value}
      language={language}
      theme="vs"
      loading={
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          Loading editor…
        </div>
      }
      options={{
        readOnly,
        fontSize: 13,
        minimap: { enabled: false },
      }}
      onChange={(val) => {
        if (val !== undefined) onChange?.(val);
      }}
    />
  );
}
