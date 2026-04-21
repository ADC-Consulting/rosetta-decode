import { cn } from "@/lib/utils";
import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { common, createLowlight } from "lowlight";
import { closeHistory } from "prosemirror-history";
import {
  Bold,
  FileCode,
  Italic,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  Strikethrough,
  Undo2,
} from "lucide-react";
import { useEffect, useRef } from "react";

const lowlight = createLowlight(common);

interface TiptapEditorProps {
  content?: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
}

interface ToolbarButtonProps {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  label: string;
  children: React.ReactNode;
}

function ToolbarButton({
  onClick,
  active = false,
  disabled = false,
  label,
  children,
}: ToolbarButtonProps): React.ReactElement {
  return (
    <div className="relative group/tip">
      <button
        type="button"
        aria-label={label}
        aria-pressed={active}
        disabled={disabled}
        onMouseDown={(e) => {
          e.preventDefault();
        }}
        onClick={(e) => {
          e.preventDefault();
          if (!disabled) onClick();
        }}
        className={cn(
          "h-7 w-7 flex items-center justify-center rounded text-sm transition-colors cursor-pointer",
          active
            ? "bg-muted text-foreground font-bold"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
          disabled && "opacity-40 cursor-not-allowed",
        )}
      >
        {children}
      </button>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute top-full left-1/2 -translate-x-1/2 mt-1.5 z-50 rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap opacity-0 transition-opacity duration-100 group-hover/tip:opacity-100"
      >
        {label}
      </div>
    </div>
  );
}

function Divider(): React.ReactElement {
  return <div className="w-px h-5 bg-border mx-0.5 self-center" />;
}

function Toolbar({
  editor,
}: {
  editor: ReturnType<typeof useEditor>;
}): React.ReactElement | null {
  if (!editor) return null;

  return (
    <div className="flex flex-wrap items-center gap-0.5 p-1 border-b border-border bg-muted/30">
      <ToolbarButton
        onClick={() => editor.chain().toggleBold().run()}
        active={editor.isActive("bold")}
        label="Bold"
      >
        <Bold size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().toggleItalic().run()}
        active={editor.isActive("italic")}
        label="Italic"
      >
        <Italic size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().toggleStrike().run()}
        active={editor.isActive("strike")}
        label="Strikethrough"
      >
        <Strikethrough size={13} />
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().toggleHeading({ level: 1 }).run()}
        active={editor.isActive("heading", { level: 1 })}
        label="Heading 1"
      >
        <span className="text-[11px] font-bold leading-none">H1</span>
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().toggleHeading({ level: 2 }).run()}
        active={editor.isActive("heading", { level: 2 })}
        label="Heading 2"
      >
        <span className="text-[11px] font-bold leading-none">H2</span>
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().toggleHeading({ level: 3 }).run()}
        active={editor.isActive("heading", { level: 3 })}
        label="Heading 3"
      >
        <span className="text-[11px] font-bold leading-none">H3</span>
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().toggleBulletList().run()}
        active={editor.isActive("bulletList")}
        label="Bullet list"
      >
        <List size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().toggleOrderedList().run()}
        active={editor.isActive("orderedList")}
        label="Ordered list"
      >
        <ListOrdered size={13} />
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().toggleBlockquote().run()}
        active={editor.isActive("blockquote")}
        label="Blockquote"
      >
        <Quote size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().toggleCodeBlock().run()}
        active={editor.isActive("codeBlock")}
        label="Code block"
      >
        <FileCode size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().setHorizontalRule().run()}
        label="Horizontal rule"
      >
        <Minus size={13} />
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().undo().run()}
        disabled={!editor.can().undo()}
        label="Undo"
      >
        <Undo2 size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().redo().run()}
        disabled={!editor.can().redo()}
        label="Redo"
      >
        <Redo2 size={13} />
      </ToolbarButton>
    </div>
  );
}

export default function TiptapEditor({
  content,
  onChange,
  readOnly = false,
}: TiptapEditorProps): React.ReactElement {
  const settingContent = useRef(false);
  const loadedContent = useRef<string | undefined>(undefined);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        codeBlock: false,
        heading: { levels: [1, 2, 3, 4, 5, 6] },
      }),
      CodeBlockLowlight.configure({ lowlight }),
    ],
    content: "",
    editable: !readOnly,
    immediatelyRender: false,
    onUpdate({ editor: e }) {
      if (!onChange || settingContent.current) return;
      onChange(e.getHTML());
    },
  });

  // Load content whenever the prop changes. The ref guards against the echo loop:
  // onUpdate → onChange → parent state → content prop → setContent → onUpdate.
  useEffect(() => {
    if (!editor || content === undefined) return;
    if (content === loadedContent.current) return;
    loadedContent.current = content;
    settingContent.current = true;
    editor.commands.setContent(content, false);
    settingContent.current = false;
    // Close the history group at the load boundary so undo can't remove loaded content.
    editor.view.dispatch(closeHistory(editor.state.tr));
  }, [editor, content]);

  return (
    <div className="rounded-md border border-border overflow-hidden">
      {!readOnly && <Toolbar editor={editor} />}
      <EditorContent
        editor={editor}
        className={cn(
          "p-3 min-h-[180px] focus:outline-none text-sm",
          // Explicit heading + list styles since Tailwind Preflight resets browser defaults
          // and @tailwindcss/typography is not installed.
          "[&_.ProseMirror]:outline-none [&_.ProseMirror]:min-h-[160px]",
          "[&_.ProseMirror_h1]:text-2xl [&_.ProseMirror_h1]:font-bold [&_.ProseMirror_h1]:mt-4 [&_.ProseMirror_h1]:mb-2",
          "[&_.ProseMirror_h2]:text-xl [&_.ProseMirror_h2]:font-bold [&_.ProseMirror_h2]:mt-3 [&_.ProseMirror_h2]:mb-2",
          "[&_.ProseMirror_h3]:text-lg [&_.ProseMirror_h3]:font-semibold [&_.ProseMirror_h3]:mt-3 [&_.ProseMirror_h3]:mb-1",
          "[&_.ProseMirror_h4]:text-base [&_.ProseMirror_h4]:font-semibold [&_.ProseMirror_h4]:mt-2 [&_.ProseMirror_h4]:mb-1",
          "[&_.ProseMirror_p]:mb-2",
          "[&_.ProseMirror_ul]:list-disc [&_.ProseMirror_ul]:pl-5 [&_.ProseMirror_ul]:mb-2",
          "[&_.ProseMirror_ol]:list-decimal [&_.ProseMirror_ol]:pl-5 [&_.ProseMirror_ol]:mb-2",
          "[&_.ProseMirror_li]:mb-0.5",
          "[&_.ProseMirror_blockquote]:border-l-4 [&_.ProseMirror_blockquote]:border-border [&_.ProseMirror_blockquote]:pl-3 [&_.ProseMirror_blockquote]:text-muted-foreground [&_.ProseMirror_blockquote]:italic [&_.ProseMirror_blockquote]:my-2",
          "[&_.ProseMirror_hr]:border-border [&_.ProseMirror_hr]:my-3",
          "[&_.ProseMirror_strong]:font-bold",
          "[&_.ProseMirror_em]:italic",
          "[&_.ProseMirror_code]:bg-muted [&_.ProseMirror_code]:rounded [&_.ProseMirror_code]:px-1 [&_.ProseMirror_code]:text-xs [&_.ProseMirror_code]:font-mono",
          "[&_.ProseMirror_pre]:bg-muted [&_.ProseMirror_pre]:rounded [&_.ProseMirror_pre]:p-3 [&_.ProseMirror_pre]:my-2 [&_.ProseMirror_pre]:overflow-x-auto",
        )}
      />
    </div>
  );
}
