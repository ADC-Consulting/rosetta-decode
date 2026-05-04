import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Editor, type OnMount } from "@monaco-editor/react";
import { Copy, Check } from "lucide-react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

// Map common fenced-code language tags to Monaco language IDs
const LANG_MAP: Record<string, string> = {
  py: "python",
  python: "python",
  pyspark: "python",
  sas: "sas",
  sql: "sql",
  sh: "shell",
  bash: "shell",
  shell: "shell",
  ts: "typescript",
  typescript: "typescript",
  js: "javascript",
  javascript: "javascript",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  r: "r",
};

function resolveLanguage(raw: string): string {
  return (LANG_MAP[raw.toLowerCase()] ?? raw.toLowerCase()) || "plaintext";
}

const LINE_HEIGHT = 19;
const PADDING = 16;
const MIN_HEIGHT = 60;
const MAX_HEIGHT = 400;

interface CodeBlockProps {
  language: string;
  value: string;
}

function CodeBlock({ language, value }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const { resolvedTheme } = useTheme();
  const monacoLang = resolveLanguage(language);

  const lineCount = value.split("\n").length;
  const height = Math.min(Math.max(lineCount * LINE_HEIGHT + PADDING, MIN_HEIGHT), MAX_HEIGHT);

  const handleCopy = () => {
    navigator.clipboard.writeText(value).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleMount: OnMount = (editor) => {
    // Force correct layout after mount
    editor.layout({ height, width: editor.getLayoutInfo().width });
  };

  return (
    <div className="relative my-2 rounded-md overflow-hidden border border-border">
      <div className="flex items-center justify-between px-3 py-1 bg-muted text-xs text-muted-foreground border-b border-border">
        <span className="font-mono">{language || "code"}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          aria-label="Copy code"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <Editor
        height={height}
        language={monacoLang}
        value={value}
        theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
        onMount={handleMount}
        options={{
          readOnly: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: "on",
          lineNumbers: "off",
          folding: false,
          renderLineHighlight: "none",
          padding: { top: 8, bottom: 8 },
          scrollbar: { vertical: lineCount * LINE_HEIGHT > MAX_HEIGHT ? "auto" : "hidden" },
        }}
      />
    </div>
  );
}

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div
      className={cn(
        "text-sm leading-relaxed",
        "[&_h1]:text-lg [&_h1]:font-semibold [&_h1]:mt-3 [&_h1]:mb-1",
        "[&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1",
        "[&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1",
        "[&_p]:my-1 [&_p]:leading-relaxed",
        "[&_ul]:my-1 [&_ul]:pl-4 [&_ul]:list-disc",
        "[&_ol]:my-1 [&_ol]:pl-4 [&_ol]:list-decimal",
        "[&_li]:my-0.5",
        "[&_strong]:font-semibold",
        "[&_em]:italic",
        "[&_a]:text-primary [&_a]:underline hover:[&_a]:opacity-80",
        "[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_blockquote]:my-2",
        "[&_table]:w-full [&_table]:text-xs [&_table]:border-collapse [&_table]:my-2",
        "[&_th]:bg-muted [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:border [&_th]:border-border",
        "[&_td]:px-2 [&_td]:py-1 [&_td]:border [&_td]:border-border",
        "[&_hr]:border-border [&_hr]:my-3",
        "[&_code]:bg-muted [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          code({ inline, className: cls, children, ...props }: any) {
            const match = /language-(\w+)/.exec(cls || "");
            const language = match?.[1] ?? "";
            const value = String(children).replace(/\n$/, "");
            if (!inline && (language || value.includes("\n"))) {
              return <CodeBlock language={language} value={value} />;
            }
            return (
              <code className={cls} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownRenderer;
