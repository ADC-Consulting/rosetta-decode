import { cn } from "@/lib/utils";
import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { common, createLowlight } from "lowlight";
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

const lowlight = createLowlight(common);

interface TiptapEditorProps {
  content?: string;
  onChange?: (html: string) => void;
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
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      aria-pressed={active}
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
        onClick={() => editor.chain().focus().toggleBold().run()}
        active={editor.isActive("bold")}
        label="Bold"
      >
        <Bold size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleItalic().run()}
        active={editor.isActive("italic")}
        label="Italic"
      >
        <Italic size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleStrike().run()}
        active={editor.isActive("strike")}
        label="Strikethrough"
      >
        <Strikethrough size={13} />
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        active={editor.isActive("heading", { level: 1 })}
        label="Heading 1"
      >
        <span className="text-[11px] font-bold leading-none">H1</span>
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        active={editor.isActive("heading", { level: 2 })}
        label="Heading 2"
      >
        <span className="text-[11px] font-bold leading-none">H2</span>
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        active={editor.isActive("heading", { level: 3 })}
        label="Heading 3"
      >
        <span className="text-[11px] font-bold leading-none">H3</span>
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        active={editor.isActive("bulletList")}
        label="Bullet list"
      >
        <List size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        active={editor.isActive("orderedList")}
        label="Ordered list"
      >
        <ListOrdered size={13} />
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        active={editor.isActive("blockquote")}
        label="Blockquote"
      >
        <Quote size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        active={editor.isActive("codeBlock")}
        label="Code block"
      >
        <FileCode size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
        label="Horizontal rule"
      >
        <Minus size={13} />
      </ToolbarButton>
      <Divider />
      <ToolbarButton
        onClick={() => editor.chain().focus().undo().run()}
        disabled={!editor.can().undo()}
        label="Undo"
      >
        <Undo2 size={13} />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().redo().run()}
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
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ codeBlock: false }),
      CodeBlockLowlight.configure({ lowlight }),
    ],
    content: content ?? "",
    editable: !readOnly,
    onUpdate({ editor: e }) {
      onChange?.(e.getHTML());
    },
  });

  return (
    <div className="rounded-md border border-border overflow-hidden">
      {!readOnly && <Toolbar editor={editor} />}
      <EditorContent
        editor={editor}
        className="prose prose-xs dark:prose-invert max-w-none p-3 min-h-[180px] focus:outline-none text-sm [&_.ProseMirror]:outline-none [&_.ProseMirror]:min-h-[160px]"
      />
    </div>
  );
}
