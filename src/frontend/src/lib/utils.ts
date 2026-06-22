import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Trigger a client-side download of a Markdown string as a `.md` file.
 *
 * Wraps the content in a `text/markdown` Blob, clicks a temporary anchor, and
 * revokes the object URL afterwards to avoid leaking memory.
 */
export function downloadMarkdown(content: string, filename: string): void {
  const blob = new Blob([content], { type: "text/markdown" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
