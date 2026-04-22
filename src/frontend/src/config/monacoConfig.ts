import type { OnMount } from "@monaco-editor/react";

/**
 * Default Monaco Editor theme.
 * Uses "vs-dark" as the fallback for monokai pro.
 * To register a custom monokai pro theme, use the editor's `defineTheme` API.
 *
 * @example
 * const editor = useRef(null);
 * useEffect(() => {
 *   if (editor.current) {
 *     editor.current.defineTheme("monokai-pro", {
 *       base: "vs-dark",
 *       inherit: true,
 *       rules: [...],
 *       colors: {...}
 *     });
 *     editor.current.setTheme("monokai-pro");
 *   }
 * }, []);
 */
export const MONACO_THEME = "vs-dark";

/**
 * Default Monaco Editor options.
 * All options are configurable and can be overridden per instance.
 */
export const MONACO_DEFAULT_OPTIONS = {
  readOnly: false,
  fontSize: 13,
  fontFamily: '"Courier New", monospace',
  minimap: { enabled: false },
  wordWrap: "off" as const,
  scrollBeyondLastLine: false,
  renderLineHighlight: "gutter" as const,
  lineNumbers: "on" as const,
  folding: true,
  formatOnPaste: true,
  formatOnType: true,
  tabSize: 2,
} as const;

/**
 * Monaco Editor options type for component props.
 * Allows partial overrides of default options.
 */
export type MonacoEditorOptions = Partial<
  typeof MONACO_DEFAULT_OPTIONS & {
    readOnly: boolean;
    fontSize: number;
  }
>;

/**
 * Merge user options with defaults.
 * User options take precedence over defaults.
 *
 * @param userOptions - Partial options to override defaults
 * @returns Merged options object
 */
export function getMonacoOptions(
  userOptions?: MonacoEditorOptions
): typeof MONACO_DEFAULT_OPTIONS {
  return {
    ...MONACO_DEFAULT_OPTIONS,
    ...userOptions,
  };
}

/**
 * Handle editor mount to enable future custom theme registration.
 * Can be used to register custom themes or set up editor-specific behavior.
 *
 * @param editor - Monaco editor instance
 * @param monaco - Monaco API
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const handleEditorMount: OnMount = (_editor, _monaco) => {
  // Reserved for future custom theme registration:
  // monaco.editor.defineTheme("monokai-pro", {...});
  // editor.setTheme("monokai-pro");
};
