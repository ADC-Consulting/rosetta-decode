```markdown
# Coding Standards

These standards apply to ALL Python code in this repository. Claude Code must
read this file before writing or modifying source code. Violations should be
caught by the `code-reviewer` skill before committing.

## General Principles

- Write clear, readable code that is self-documenting
- Follow the principle of least surprise
- Keep functions small and focused on a single responsibility
- Avoid premature optimization
- Don't repeat yourself (DRY)

## Naming Conventions

### Variables and Functions

- Use `snake_case` for variables and function names
- Use descriptive names that convey purpose
- Avoid single-letter names except for loop counters (`i`, `j`, `k`) or coordinates (`x`, `y`, `z`)
- Boolean variables should start with `is_`, `has_`, `can_`, or similar prefixes

### Classes

- Use `PascalCase` for class names
- Use nouns or noun phrases for class names

### Constants

- Use `UPPER_SNAKE_CASE` for constants
- Define constants at module level

## Code Structure

### Imports

- Group imports in the following order:
  1. Standard library imports
  2. Third-party library imports
  3. Local application imports
- Separate each group with a blank line
- Sort imports alphabetically within each group

### Functions

- Keep functions under 50 lines when possible
- Limit function parameters to 5 or fewer
- Use default parameter values where appropriate
- Return early to avoid deep nesting

### Classes

- Keep classes focused on a single responsibility
- Prefer composition over inheritance
- Use properties for computed attributes

## Documentation

### Docstrings

- Use docstrings for all public modules, classes, and functions
- Follow NumPy or Google docstring style consistently
- Include parameters, return values, and exceptions in docstrings

### Comments

- Write comments to explain _why_, not _what_
- Keep comments up to date with code changes
- Avoid obvious comments that repeat the code

## Error Handling

- Use specific exception types rather than bare `except`
- Handle exceptions at the appropriate level
- Provide meaningful error messages
- Log errors with sufficient context for debugging

## Formatting

- Use 4 spaces for indentation (no tabs)
- Limit lines to 100 characters (enforced by ruff)
- Use blank lines to separate logical sections
- Remove trailing whitespace

## Type Hints

- Use type hints for function parameters and return values
- Use `Optional` for parameters that can be `None`
- Import types from `typing` module as needed

## Project-Specific Rules (SAS Migration Tool)

- Every generated Python file must begin with a provenance comment block:
  `# Generated from SAS: <source_file> (lines <start>-<end>)`
- Any `if CLOUD:` branching MUST live behind the `ComputeBackend` abstraction,
  never inside business logic
- New SAS construct handlers MUST ship with a reconciliation test in the same PR
- Hard-coded values extracted from SAS must be flagged with `# TODO(business-review)`
```
