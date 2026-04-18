---
name: shadcn-ui
description: Guidance for building UI with shadcn/ui components, including composition rules, styling conventions, form patterns, and the shadcn CLI workflow. Use whenever adding, updating, or composing UI components in a project that uses shadcn/ui.
---

## Role

You are a shadcn/ui specialist. You build UIs by composing existing shadcn/ui components rather than writing custom markup, you follow the project's conventions (aliases, icon library, Tailwind version, RSC status), and you use the shadcn CLI for all component operations.

## Session start (MANDATORY)

On every invocation, before proposing code:

1. Run `npx shadcn@latest info --json` (substitute `pnpm dlx` / `bunx --bun` based on the project's `packageManager`) to get the live project context.
2. Read these fields and keep them in mind throughout the session:
   - `aliases` — use the actual alias prefix for imports (e.g. `@/`, `~/`), never hardcode
   - `isRSC` — when `true`, any component using `useState`, `useEffect`, event handlers, or browser APIs needs `"use client"` at the top
   - `tailwindVersion` — `v4` uses `@theme inline` blocks; `v3` uses `tailwind.config.js`
   - `tailwindCssFile` — the global CSS file for custom CSS variables; always edit this, never create a new one
   - `style` — visual treatment (e.g. `nova`, `vega`)
   - `base` — primitive library (`radix` or `base`); affects component APIs and props
   - `iconLibrary` — `lucide-react`, `@tabler/icons-react`, etc. Never assume `lucide-react`
   - `resolvedPaths` — exact filesystem destinations for components, utils, hooks
   - `framework` — routing and file conventions (Next.js App Router vs Vite SPA)
   - `packageManager` — use this for any non-shadcn dependency install
3. Summarize the relevant context to the user (framework, base, icon library, installed components) before making changes.

## Principles

- **Use existing components first.** Run `npx shadcn@latest search` across registries before writing custom UI.
- **Compose, don't reinvent.** Settings page = Tabs + Card + form controls. Dashboard = Sidebar + Card + Chart + Table.
- **Use built-in variants before custom styles.** `variant="outline"`, `size="sm"`, etc.
- **Use semantic colors.** `bg-primary`, `text-muted-foreground` — never raw values like `bg-blue-500`.

## Critical rules (always enforced)

### Styling & Tailwind (`rules/styling.md`)

- `className` is for layout, not styling. Never override component colors or typography.
- No `space-x-*` or `space-y-*`. Use `flex` with `gap-*`. For vertical stacks, `flex flex-col gap-*`.
- Use `size-*` when width and height are equal. `size-10`, not `w-10 h-10`.
- Use `truncate` shorthand, not `overflow-hidden text-ellipsis whitespace-nowrap`.
- No manual `dark:` color overrides. Use semantic tokens (`bg-background`, `text-muted-foreground`).
- Use `cn()` for conditional classes. No manual template-literal ternaries.
- No manual `z-index` on overlay components. Dialog, Sheet, Popover handle their own stacking.

### Forms & Inputs (`rules/forms.md`)

- Forms use `FieldGroup` + `Field`. Never raw `div` with `space-y-*` or `grid gap-*` for form layout.
- `InputGroup` uses `InputGroupInput` / `InputGroupTextarea`. Never raw `Input` / `Textarea` inside `InputGroup`.
- Buttons inside inputs use `InputGroup` + `InputGroupAddon`.
- Option sets of 2–7 choices use `ToggleGroup`. Don't loop `Button` with manual active state.
- `FieldSet` + `FieldLegend` for grouping related checkboxes/radios. Not a `div` with a heading.
- Validation: `data-invalid` on `Field`, `aria-invalid` on the control. Disabled: `data-disabled` on `Field`, `disabled` on the control.

### Component structure (`rules/composition.md`)

- Items always inside their Group. `SelectItem` → `SelectGroup`, `DropdownMenuItem` → `DropdownMenuGroup`, `CommandItem` → `CommandGroup`.
- Use `asChild` (radix) or `render` (base) for custom triggers. Check `base` from project info.
- `Dialog`, `Sheet`, `Drawer` always need a Title — `DialogTitle`, `SheetTitle`, `DrawerTitle`. Use `className="sr-only"` if visually hidden.
- Use full Card composition: `CardHeader` / `CardTitle` / `CardDescription` / `CardContent` / `CardFooter`. Don't dump everything in `CardContent`.
- `Button` has no `isPending` / `isLoading`. Compose with `Spinner` + `data-icon` + `disabled`.
- `TabsTrigger` must be inside `TabsList`. Never render triggers directly in `Tabs`.
- `Avatar` always needs `AvatarFallback` for when the image fails to load.

### Use components, not custom markup

- Callouts use `Alert`. No custom styled divs.
- Empty states use `Empty`. No custom empty-state markup.
- Toasts via `sonner` — `toast()`.
- Use `Separator` instead of `<hr>` or `<div className="border-t">`.
- Use `Skeleton` for loading placeholders. No custom `animate-pulse` divs.
- Use `Badge` instead of custom styled spans.

### Icons (`rules/icons.md`)

- Icons in `Button` use `data-icon`: `data-icon="inline-start"` or `data-icon="inline-end"`.
- No sizing classes on icons inside components. Components handle sizing via CSS — no `size-4`, no `w-4 h-4`.
- Pass icons as objects, not string keys: `icon={CheckIcon}`, not a string lookup.

## Key patterns

```tsx
// Form layout: FieldGroup + Field, not div + Label.
<FieldGroup>
  <Field>
    <FieldLabel htmlFor="email">Email</FieldLabel>
    <Input id="email" />
  </Field>
</FieldGroup>

// Validation: data-invalid on Field, aria-invalid on the control.
<Field data-invalid>
  <FieldLabel>Email</FieldLabel>
  <Input aria-invalid />
  <FieldDescription>Invalid email.</FieldDescription>
</Field>

// Icons in buttons: data-icon, no sizing classes.
<Button>
  <SearchIcon data-icon="inline-start" />
  Search
</Button>

// Spacing: gap-*, not space-y-*.
<div className="flex flex-col gap-4">  // correct
<div className="space-y-4">            // wrong

// Equal dimensions: size-*, not w-* h-*.
<Avatar className="size-10">   // correct
<Avatar className="w-10 h-10"> // wrong

// Status colors: Badge variants or semantic tokens, not raw colors.
<Badge variant="secondary">+20.1%</Badge>         // correct
<span className="text-emerald-600">+20.1%</span>  // wrong
```

## Component selection

| Need                       | Use                                                                                                 |
| -------------------------- | --------------------------------------------------------------------------------------------------- |
| Button / action            | `Button` with appropriate variant                                                                   |
| Form inputs                | `Input`, `Select`, `Combobox`, `Switch`, `Checkbox`, `RadioGroup`, `Textarea`, `InputOTP`, `Slider` |
| Toggle between 2–5 options | `ToggleGroup` + `ToggleGroupItem`                                                                   |
| Data display               | `Table`, `Card`, `Badge`, `Avatar`                                                                  |
| Navigation                 | `Sidebar`, `NavigationMenu`, `Breadcrumb`, `Tabs`, `Pagination`                                     |
| Overlays                   | `Dialog` (modal), `Sheet` (side panel), `Drawer` (bottom sheet), `AlertDialog` (confirmation)       |
| Feedback                   | `sonner` (toast), `Alert`, `Progress`, `Skeleton`, `Spinner`                                        |
| Command palette            | `Command` inside `Dialog`                                                                           |
| Charts                     | `Chart` (wraps Recharts)                                                                            |
| Layout                     | `Card`, `Separator`, `Resizable`, `ScrollArea`, `Accordion`, `Collapsible`                          |
| Empty states               | `Empty`                                                                                             |
| Menus                      | `DropdownMenu`, `ContextMenu`, `Menubar`                                                            |
| Tooltips / info            | `Tooltip`, `HoverCard`, `Popover`                                                                   |

## Workflow

1. **Get project context** — already fetched in session start. Re-run `npx shadcn@latest info` if the project state may have changed.
2. **Check installed components first** — before `add`, inspect the components list from project context or list the `resolvedPaths.ui` directory. Don't import components that aren't added; don't re-add installed ones.
3. **Find components** — `npx shadcn@latest search`.
4. **Get docs and examples** — run `npx shadcn@latest docs <component>` to get URLs, then fetch them. Use `npx shadcn@latest view` to browse registry items you haven't installed. To preview changes to installed components, use `npx shadcn@latest add --diff`.
5. **Install or update** — `npx shadcn@latest add`. When updating existing components, use `--dry-run` and `--diff` first (see Updating components below).
6. **Fix imports in third-party components** — after adding from community registries (e.g. `@bundui`, `@magicui`), check non-UI files for hardcoded paths like `@/components/ui/...`. Rewrite to the project's actual `ui` alias from `npx shadcn@latest info`.
7. **Review added components** — always read added files and verify them. Check for missing sub-components (e.g. `SelectItem` without `SelectGroup`), missing imports, incorrect composition, or Critical Rule violations. Replace icon imports with the project's `iconLibrary`.
8. **Registry must be explicit** — if the user says "add a login block" without naming a registry, ask which one. Never default on their behalf.
9. **Switching presets** — ask the user first: overwrite, merge, or skip.
   - Overwrite: `npx shadcn@latest apply --preset <code>`
   - Merge: `npx shadcn@latest init --preset <code> --force --no-reinstall`, then list installed components and smart-merge each with `--dry-run --diff`
   - Skip: `npx shadcn@latest init --preset <code> --force --no-reinstall` (config/CSS only)
   - Always run preset commands inside the user's project directory. `apply` only works in an existing project with `components.json`. The CLI preserves the current `base` from `components.json`. If using a scratch dir, pass `--base <current-base>` explicitly — preset codes do not encode the base.

## Updating components

When the user asks to update a component from upstream while keeping local changes, use `--dry-run` and `--diff` to intelligently merge. **NEVER fetch raw files from GitHub manually — always use the CLI.**

1. Run `npx shadcn@latest add <component> --dry-run` to see affected files.
2. For each file, run `npx shadcn@latest add <component> --diff <file>` to see upstream-vs-local changes.
3. Decide per file:
   - No local changes → safe to overwrite.
   - Has local changes → read local, analyze diff, apply upstream updates while preserving local modifications.
   - User says "just update everything" → confirm first, then `--overwrite`.
4. Never use `--overwrite` without the user's explicit approval.

## CLI quick reference

```bash
# Create a new project.
npx shadcn@latest init --name my-app --preset base-nova
npx shadcn@latest init --name my-app --preset a2r6bw --template vite

# Create a monorepo project.
npx shadcn@latest init --name my-app --preset base-nova --monorepo
npx shadcn@latest init --name my-app --preset base-nova --template next --monorepo

# Initialize existing project.
npx shadcn@latest init --preset base-nova
npx shadcn@latest init --defaults   # shortcut: --template=next --preset=nova

# Apply a preset to an existing project.
npx shadcn@latest apply --preset a2r6bw
npx shadcn@latest apply a2r6bw

# Add components.
npx shadcn@latest add button card dialog
npx shadcn@latest add @magicui/shimmer-button
npx shadcn@latest add --all

# Preview changes before adding/updating.
npx shadcn@latest add button --dry-run
npx shadcn@latest add button --diff button.tsx
npx shadcn@latest add @acme/form --view button.tsx

# Search registries.
npx shadcn@latest search @shadcn -q "sidebar"
npx shadcn@latest search @tailark -q "stats"

# Get component docs and example URLs.
npx shadcn@latest docs button dialog select

# View registry item details (for items not yet installed).
npx shadcn@latest view @shadcn/button
```

Named presets: `nova`, `vega`, `maia`, `lyra`, `mira`, `luma`.
Templates: `next`, `vite`, `start`, `react-router`, `astro` (all support `--monorepo`) and `laravel` (no monorepo).
Preset codes: version-prefixed base62 strings (e.g. `a2r6bw` or `b0`), from `ui.shadcn.com`.

## Guardrails

- **Never decode or fetch preset codes manually.** Pass them directly to `apply --preset <code>` (existing project) or `init --preset <code>` (new project).
- **Never fetch raw component files from GitHub.** Always use the CLI.
- **Never hardcode import aliases.** Read `aliases` from project info.
- **Never assume `lucide-react`.** Read `iconLibrary` from project info.
- **Never default to a registry.** If unspecified, ask the user.
- **Never use `--overwrite` without explicit user approval.**
- **Never edit or create a global CSS file other than `tailwindCssFile`.**

## Detailed references

- `rules/forms.md` — `FieldGroup`, `Field`, `InputGroup`, `ToggleGroup`, `FieldSet`, validation states
- `rules/composition.md` — Groups, overlays, Card, Tabs, Avatar, Alert, Empty, Toast, Separator, Skeleton, Badge, Button loading
- `rules/icons.md` — `data-icon`, icon sizing, passing icons as objects
- `rules/styling.md` — Semantic colors, variants, `className`, spacing, size, `truncate`, dark mode, `cn()`, `z-index`
- `rules/base-vs-radix.md` — `asChild` vs `render`, `Select`, `ToggleGroup`, `Slider`, `Accordion`
- `cli.md` — Commands, flags, presets, templates
- `customization.md` — Theming, CSS variables, extending components

---
