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
      "LABEL", "ATTRIB", "ARRAY", "PUT", "RENAME", "CALL",
      "LIBNAME", "FILENAME", "OPTIONS", "TITLE", "FOOTNOTE",
      "SELECT", "WHEN", "OTHERWISE", "CLASS", "VAR", "MODEL", "TABLES",
      "FREQ", "MEANS", "SORT", "PRINT", "SQL", "CREATE", "TABLE", "AS",
      "FROM", "GROUP", "HAVING", "ORDER", "INTO", "INSERT", "DELETE",
      "UPDATE", "JOIN", "ON", "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN",
      "CASE", "DISTINCT", "UNION", "OUTER", "INNER", "LEFT", "RIGHT", "FULL",
      "DESCENDING", "ASCENDING",
      "ERROR", "LEAVE", "CONTINUE", "STOP", "ABORT", "LINK", "GOTO", "RETURN",
      "GT", "LT", "EQ", "NE", "GE", "LE",
    ],
    macroKeywords: [
      "%LET", "%IF", "%THEN", "%ELSE", "%DO", "%END",
      "%MACRO", "%MEND", "%INCLUDE", "%PUT",
      "%LOCAL", "%GLOBAL", "%RETURN", "%ABORT",
      "%SYSFUNC", "%QSYSFUNC", "%EVAL", "%SYSEVALF",
      "%STR", "%NRSTR", "%QUOTE", "%NRQUOTE",
      "%SYMEXIST", "%SYMGLOBL", "%SYMLOCAL",
      "%UPCASE", "%LOWCASE", "%TRIM", "%LEFT",
      "%SCAN", "%SUBSTR", "%INDEX",
    ],
    sasFunctions: [
      "missing", "substr", "trim", "input", "catx", "compress", "scan",
      "upcase", "lowcase", "strip", "length", "index", "tranwrd", "coalescec",
      "coalesce", "int", "round", "sum", "mean", "min", "max", "abs", "mod",
      "floor", "ceil", "lag", "dif", "today", "date", "time", "datetime",
      "datepart", "timepart", "mdy", "ymd", "year", "month", "day", "hour",
      "minute", "second", "weekday", "qtr",
      "intck", "intnx", "yrdif", "datdif", "dhms", "hms",
      "n", "nmiss", "range", "std", "var", "cv", "median",
      "countw", "count", "find", "findc", "reverse", "repeat",
      "trimn", "cats", "catt", "catn", "prxmatch", "prxchange", "prxparse",
      "ifc", "ifn", "choosec", "choosen",
    ],
    tokenizer: {
      root: [
        [/\/\*/, "comment", "@blockComment"],
        [/^[ \t]*\*[^;]*;/, "comment"],
        [
          /%[a-zA-Z]+/,
          { cases: { "@macroKeywords": "keyword.macro", "@default": "variable.macro" } },
        ],
        [/&[a-zA-Z_][a-zA-Z0-9_]*/, "variable"],
        [
          /[a-zA-Z_][a-zA-Z0-9_]*/,
          {
            cases: {
              "@keywords": "keyword",
              "@sasFunctions": "keyword.function",
              "@default": "identifier",
            },
          },
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
      { token: "keyword", foreground: "569CD6", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "c678dd", fontStyle: "bold" },
      { token: "keyword.function", foreground: "569CD6", fontStyle: "bold" },
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
      { token: "keyword", foreground: "0070C0", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "8700af", fontStyle: "bold" },
      { token: "keyword.function", foreground: "0070C0", fontStyle: "bold" },
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

  monaco.languages.registerFoldingRangeProvider("sas", {
    provideFoldingRanges(model) {
      const ranges: monaco.languages.FoldingRange[] = [];
      const lines = model.getLinesContent();
      const n = lines.length;

      // Stack-based fold for DATA/PROC...RUN/QUIT and DO...END
      const dataProc: number[] = []; // stack of 1-based start lines for DATA/PROC
      const doStack: number[] = []; // stack of 1-based start lines for DO

      for (let i = 0; i < n; i++) {
        const line = lines[i].trim().toUpperCase();
        const lineNo = i + 1; // Monaco uses 1-based line numbers

        if (/^(DATA|PROC)\b/.test(line)) {
          dataProc.push(lineNo);
        } else if (/^RUN\s*;/.test(line) || /^QUIT\s*;/.test(line)) {
          const start = dataProc.pop();
          if (start !== undefined && lineNo > start) {
            ranges.push({
              start,
              end: lineNo,
              kind: monaco.languages.FoldingRangeKind.Region,
            });
          }
        } else if (/\bDO\s*;/.test(line) || /\bDO\b/.test(line)) {
          doStack.push(lineNo);
        } else if (/^END\s*;/.test(line)) {
          const start = doStack.pop();
          if (start !== undefined && lineNo > start) {
            ranges.push({
              start,
              end: lineNo,
              kind: monaco.languages.FoldingRangeKind.Region,
            });
          }
        }
      }

      return ranges;
    },
  });
}
