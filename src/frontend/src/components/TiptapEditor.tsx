import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import { createLowlight, common } from "lowlight";
import { useState } from "react";
import { Bold, Italic, Code, FileCode } from "lucide-react";

const lowlight = createLowlight(common);

interface TiptapEditorProps {
  content?: string;
  onChange?: (html: string) => void;
  readOnly?: boolean;
}

function Toolbar({ editor }: { editor: ReturnType<typeof useEditor> }): React.ReactElement | null {
  if (!editor) return null;

  return (
    <div className="flex gap-1 p-1 border-b border-border bg-muted/30">
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleBold().run()}
        aria-label="Bold"
        aria-pressed={editor.isActive("bold")}
        className={`p-1.5 rounded text-sm transition-colors ${
          editor.isActive("bold")
            ? "bg-foreground text-background"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
      >
        <Bold size={14} />
      </button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleItalic().run()}
        aria-label="Italic"
        aria-pressed={editor.isActive("italic")}
        className={`p-1.5 rounded text-sm transition-colors ${
          editor.isActive("italic")
            ? "bg-foreground text-background"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
      >
        <Italic size={14} />
      </button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleCode().run()}
        aria-label="Inline code"
        aria-pressed={editor.isActive("code")}
        className={`p-1.5 rounded text-sm transition-colors ${
          editor.isActive("code")
            ? "bg-foreground text-background"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
      >
        <Code size={14} />
      </button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        aria-label="Code block"
        aria-pressed={editor.isActive("codeBlock")}
        className={`p-1.5 rounded text-sm transition-colors ${
          editor.isActive("codeBlock")
            ? "bg-foreground text-background"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
      >
        <FileCode size={14} />
      </button>
    </div>
  );
}

export default function TiptapEditor({
  content,
  onChange,
  readOnly = false,
}: TiptapEditorProps): React.ReactElement {
  const [isEditing, setIsEditing] = useState(!readOnly);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ codeBlock: false }),
      CodeBlockLowlight.configure({ lowlight }),
    ],
    content: content ?? "",
    editable: isEditing,
    onUpdate({ editor: e }) {
      onChange?.(e.getHTML());
    },
  });

  function toggleEdit(): void {
    const next = !isEditing;
    setIsEditing(next);
    editor?.setEditable(next);
  }

  return (
    <div className="rounded-md border border-border overflow-hidden">
      {readOnly ? (
        <div className="flex justify-end p-1 border-b border-border bg-muted/30">
          <button
            type="button"
            onClick={toggleEdit}
            className="text-xs px-2 py-1 rounded border border-border text-muted-foreground hover:text-foreground transition-colors"
          >
            {isEditing ? "Done" : "Edit"}
          </button>
        </div>
      ) : (
        <Toolbar editor={editor} />
      )}
      {readOnly && isEditing && <Toolbar editor={editor} />}
      <EditorContent
        editor={editor}
        className="prose prose-sm dark:prose-invert max-w-none p-3 min-h-[200px] focus:outline-none"
      />
    </div>
  );
}
