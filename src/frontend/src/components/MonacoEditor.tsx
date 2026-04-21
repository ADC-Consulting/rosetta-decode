import {
  MONACO_THEME,
  getMonacoOptions,
  handleEditorMount,
  type MonacoEditorOptions,
} from "@/config/monacoConfig";
import { Editor } from "@monaco-editor/react";

interface MonacoEditorProps {
  value: string;
  language?: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
  theme?: string;
  editorOptions?: MonacoEditorOptions;
}

export default function MonacoEditor({
  value,
  language = "python",
  onChange,
  readOnly = false,
  height = "500px",
  theme = MONACO_THEME,
  editorOptions,
}: MonacoEditorProps): React.ReactElement {
  const mergedOptions = getMonacoOptions({
    readOnly,
    ...editorOptions,
  });

  return (
    <Editor
      height={height}
      value={value}
      language={language}
      theme={theme}
      loading={
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          Loading editor…
        </div>
      }
      options={mergedOptions}
      onChange={(val) => {
        if (val !== undefined) onChange?.(val);
      }}
      onMount={handleEditorMount}
    />
  );
}
