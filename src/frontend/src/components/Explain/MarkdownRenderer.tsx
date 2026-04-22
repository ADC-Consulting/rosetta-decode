import MonacoEditor from "@/components/MonacoEditor";

interface MarkdownRendererProps {
  content: string;
}

function renderInlineMarkdown(text: string): React.ReactNode[] {
  // Handle **bold** and `code` inline patterns
  const parts: React.ReactNode[] = [];
  // Combined regex: **bold** or `code`
  const pattern = /(\*\*(.+?)\*\*|`([^`]+)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    if (match[0].startsWith("**")) {
      parts.push(<strong key={match.index}>{match[2]}</strong>);
    } else {
      parts.push(
        <code
          key={match.index}
          className="font-mono text-xs bg-muted px-1 rounded"
        >
          {match[3]}
        </code>,
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps): React.ReactElement {
  const segments = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2 text-sm">
      {segments.map((segment, i) => {
        if (segment.startsWith("```")) {
          // Extract language and code
          const withoutFences = segment.slice(3, segment.length - 3);
          const newlineIdx = withoutFences.indexOf("\n");
          const lang = newlineIdx > -1 ? withoutFences.slice(0, newlineIdx).trim() : "";
          const code = newlineIdx > -1 ? withoutFences.slice(newlineIdx + 1) : withoutFences;

          return (
            <MonacoEditor
              key={i}
              value={code}
              language={lang || "plaintext"}
              readOnly
              height="160px"
            />
          );
        }

        // Text segment — render inline markdown line by line
        const lines = segment.split("\n");
        return (
          <div key={i}>
            {lines.map((line, j) => (
              <p key={j} className={line === "" ? "h-2" : undefined}>
                {renderInlineMarkdown(line)}
              </p>
            ))}
          </div>
        );
      })}
    </div>
  );
}
