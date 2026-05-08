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
      "RENAME", "LABEL", "ATTRIB", "ARRAY", "LINK", "RETURN", "GOTO",
      "STOP", "ABORT", "FILE", "PUT", "GET", "INFILE", "OPTIONS", "LIBNAME",
      "FILENAME", "FOOTNOTE", "TITLE", "ODS", "MISSING", "FIRSTOBS", "OBS",
      "CROSS", "MONOTONIC", "CALCULATED", "SEPARATED", "TRIMMED",
      "COALESCE", "EXCEPT", "INTERSECT", "CORRESPONDING",
      "CONNECTION", "DISCONNECT", "EXECUTE", "RESET",
      "WEIGHT", "TYPES", "WAYS", "NWAY", "NOPRINT", "MISSING",
    ],

    macroKeywords: [
      "%LET", "%IF", "%THEN", "%ELSE", "%DO", "%END",
      "%MACRO", "%MEND", "%INCLUDE", "%PUT", "%SYSFUNC",
      "%EVAL", "%SYSEVALF", "%NRSTR", "%STR", "%QUOTE",
      "%BQUOTE", "%NRBQUOTE", "%SCAN", "%SUBSTR", "%UPCASE",
      "%LOWCASE", "%TRIM", "%LEFT", "%RIGHT", "%LENGTH",
      "%GLOBAL", "%LOCAL", "%SYSGET", "%SYMGET", "%SYMPUT",
      "%SYMPUTX", "%NOBS", "%ABORT", "%RETURN", "%GOTO",
    ],

    autoVars: [
      "_N_", "_ERROR_", "_ALL_", "_NUMERIC_", "_CHARACTER_",
      "_NAME_", "_TYPE_", "_LABEL_", "_FORMAT_",
    ],

    tokenizer: {
      root: [
        // Block comments /* ... */
        [/\/\*/, "comment", "@blockComment"],

        // Line comments: * text; — must start a statement (approximated as line-start)
        [/^\s*\*[^;]*;/, "comment"],

        // Macro keywords (%MACRO, %LET, %IF …)
        [
          /%[a-zA-Z][a-zA-Z0-9_]*/,
          {
            cases: {
              "@macroKeywords": "keyword.macro",
              "@default": "variable.macro",
            },
          },
        ],

        // Macro variable references: &&var. or &var
        [/&&?[a-zA-Z_][a-zA-Z0-9_]*\.?/, "variable.macro"],

        // Format/informat names — identifier immediately followed by digit(s) and a dot
        // e.g. DATE9.  DOLLAR12.2  MMDDYY10.  BEST32.
        [/[a-zA-Z_][a-zA-Z0-9_]*\d+\.\d*/, "type.format"],

        // Keywords and identifiers (must come after format rule)
        [
          /[a-zA-Z_][a-zA-Z0-9_]*/,
          {
            cases: {
              "@keywords": "keyword",
              "@autoVars": "variable.predefined",
              "@default": "identifier",
            },
          },
        ],

        // Strings
        [/"([^"\\]|\\.)*"/, "string"],
        [/'([^'\\]|\\.)*'/, "string"],

        // Numbers
        [/\d+\.?\d*([eE][+-]?\d+)?/, "number"],

        // Operators
        [/[=<>!|+\-*/]/, "operator"],

        // Delimiters
        [/[;(),[\]{}.]/, "delimiter"],
      ],

      blockComment: [
        [/[^/*]+/, "comment"],
        [/\*\//, "comment", "@pop"],
        [/[/*]/, "comment"],
      ],
    },
  });

  // SAS Studio-inspired light theme
  monaco.editor.defineTheme("sas-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "0000C0", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "7030A0", fontStyle: "bold" },
      { token: "variable.macro", foreground: "7030A0" },
      { token: "variable.predefined", foreground: "000080", fontStyle: "italic" },
      { token: "type.format", foreground: "007070" },
      { token: "string", foreground: "A31515" },
      { token: "comment", foreground: "008000", fontStyle: "italic" },
      { token: "number", foreground: "007070" },
      { token: "operator", foreground: "000000" },
      { token: "delimiter", foreground: "000000" },
      { token: "identifier", foreground: "000000" },
    ],
    colors: {
      "editor.background": "#FFFFFF",
      "editor.foreground": "#000000",
      "editorLineNumber.foreground": "#999999",
    },
  });

  // VS Code standard dark theme for SAS
  monaco.editor.defineTheme("sas-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "569CD6", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "C586C0", fontStyle: "bold" },
      { token: "variable.macro", foreground: "C586C0" },
      { token: "variable.predefined", foreground: "4EC9B0", fontStyle: "italic" },
      { token: "type.format", foreground: "4EC9B0" },
      { token: "string", foreground: "CE9178" },
      { token: "comment", foreground: "6A9955", fontStyle: "italic" },
      { token: "number", foreground: "B5CEA8" },
      { token: "operator", foreground: "D4D4D4" },
      { token: "delimiter", foreground: "D4D4D4" },
      { token: "identifier", foreground: "D4D4D4" },
    ],
    colors: {
      "editor.background": "#1E1E1E",
      "editor.foreground": "#D4D4D4",
    },
  });
}
