import type { Monaco } from "@monaco-editor/react";

export function registerSasLanguage(monaco: Monaco): void {
  if (
    monaco.languages.getLanguages().some((l: { id: string }) => l.id === "sas")
  )
    return;

  monaco.languages.register({ id: "sas" });

  monaco.languages.setMonarchTokensProvider("sas", {
    ignoreCase: true,
    keywords: [
      "DATA", "SET", "RUN", "PROC", "QUIT", "IF", "THEN", "ELSE", "DO",
      "END", "BY", "WHERE", "KEEP", "DROP", "MERGE", "OUTPUT", "RETAIN",
      "LENGTH", "FORMAT", "INFORMAT", "INPUT", "CARDS", "DATALINES",
      "SELECT", "WHEN", "OTHERWISE", "CLASS", "VAR", "MODEL", "TABLES",
      "FREQ", "MEANS", "SORT", "PRINT", "SQL", "CREATE", "TABLE", "AS",
      "FROM", "GROUP", "HAVING", "ORDER", "INTO", "INSERT", "DELETE",
      "UPDATE", "JOIN", "ON", "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN",
      "CASE", "DISTINCT", "UNION", "OUTER", "INNER", "LEFT", "RIGHT", "FULL",
    ],
    macroKeywords: [
      "%LET", "%IF", "%THEN", "%ELSE", "%DO", "%END",
      "%MACRO", "%MEND", "%INCLUDE", "%PUT",
    ],
    tokenizer: {
      root: [
        [/\/\*/, "comment", "@blockComment"],
        [/^\s*\*[^;]*;/, "comment"],
        [
          /%[a-zA-Z]+/,
          { cases: { "@macroKeywords": "keyword.macro", "@default": "variable.macro" } },
        ],
        [/&[a-zA-Z_][a-zA-Z0-9_]*/, "variable"],
        [
          /[a-zA-Z_][a-zA-Z0-9_]*/,
          { cases: { "@keywords": "keyword", "@default": "identifier" } },
        ],
        [/"([^"\\]|\\.)*"/, "string"],
        [/'([^'\\]|\\.)*'/, "string"],
        [/\d+\.?\d*([eE][+-]?\d+)?/, "number"],
        [/[=<>!|+\-*/]/, "operator"],
        [/[;(),]/, "delimiter"],
      ],
      blockComment: [
        [/[^/*]+/, "comment"],
        [/\*\//, "comment", "@pop"],
        [/[/*]/, "comment"],
      ],
    },
  });

  monaco.editor.defineTheme("sas-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "4fc1ff", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "c678dd", fontStyle: "bold" },
      { token: "variable", foreground: "e5c07b" },
      { token: "variable.macro", foreground: "e5c07b" },
      { token: "string", foreground: "e06c75" },
      { token: "comment", foreground: "5c6370", fontStyle: "italic" },
      { token: "number", foreground: "d19a66" },
      { token: "operator", foreground: "abb2bf" },
      { token: "delimiter", foreground: "abb2bf" },
      { token: "identifier", foreground: "abb2bf" },
    ],
    colors: { "editor.background": "#1e1e1e" },
  });

  monaco.editor.defineTheme("sas-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "0070c1", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "8700af", fontStyle: "bold" },
      { token: "variable", foreground: "795e26" },
      { token: "variable.macro", foreground: "795e26" },
      { token: "string", foreground: "a31515" },
      { token: "comment", foreground: "008000", fontStyle: "italic" },
      { token: "number", foreground: "09885a" },
      { token: "operator", foreground: "000000" },
      { token: "delimiter", foreground: "000000" },
      { token: "identifier", foreground: "000000" },
    ],
    colors: { "editor.background": "#ffffff" },
  });
}
