# Engineering standard

Use Google's language guides as references:
- Rust: https://google.github.io/styleguide/rustguide.html
- Python: https://google.github.io/styleguide/pyguide.html
- TypeScript: https://google.github.io/styleguide/tsguide.html

Repository contracts, declared language/framework versions and configured
formatters take precedence. Google-internal build, concurrency, module and
framework conventions are not portable requirements. Avoid layout-only
rewrites, unused abstractions and new APIs without consumers. Generated or
vendored code is corrected at its owner, not restyled by hand.

Treat code entropy as continuous pressure. Actively look for code and concepts
that can be removed in every review, including unchanged parts of the named
owners. Existing code must justify its continued complexity; do not wait for a
bug, lint finding or explicit cleanup ticket. Simplification and deletion are
review outcomes, not optional polish after correctness.

Inspect these questions in the actual call path:

- Authorship and location: first-party executable code follows this contract
  wherever it lives, including agent/fleet-local scripts, skills, helpers and
  one-off task code. Model-written code is first-party code, not a generated-code
  exclusion. Trace the repositories and environments that actually execute it;
  a green parent checkout does not cover another repository or workspace. Check
  their real local/commit gates and whether automatic commit failures reach the
  author. Inventory downloaded dependencies and frozen source artifacts with
  ownership evidence; a directory called scratch is not itself an exemption.
- Organization and names: one owner per fact; meaningful domain types and
  named fields for values that can be confused; imports reveal dependencies.
- Consolidation and simplification: look for duplicated decisions, validation,
  state and pipelines; check structural twins when fixing a bug. Route real
  callers through the existing or shared owner and remove the obsolete path.
  Separate shared mechanism from domain judgment; retaining two paths needs
  a concrete, falsifiable constraint. Prefer a function for a small shared
  tail and a class only for a substantial common lifecycle. Remove redundant
  wrappers, aliases, flags and abstractions rather than relocating them.
  Describe what becomes simpler; do not generalize for hypothetical callers.
- Unused code: aggressively trace real non-test consumers of application
  functions, types, exports, branches, flags, configuration and compatibility
  paths. Tests do not count as use: a test that only exercises an otherwise
  unused API is removed with that API. Public visibility, an export, a README
  example or historical design intent is not proof of a current consumer.
  Verify runtime call paths, registered framework/plugin doors, CLI/tool entry
  points and concrete supported operator workflows; cite their owners. Check
  external integration constraints before claiming a public door is unused.
  Do not add a caller, wrapper, whitelist, scanner exception or new feature to
  make dead code appear necessary. Deliberate test helpers belong with test
  support and must serve meaningful tests; they do not justify shipping an
  unused application API. Remove orphan tests, fixtures, dependencies and docs
  with deleted behavior, while retaining coverage of behavior still required.
- The bitter lesson: for interpretation and judgment over unstructured inputs,
  challenge hand-built semantic rules, regex extraction, source-specific recipes
  and prompt-side decision trees. Prefer general model capabilities producing
  typed results, with source evidence preserved. Code owns exact parsing,
  validation, persistence, coordination and measurable constraints. Inspect
  existing heuristics as well as new ones; polishing or sharing a heuristic
  does not justify it. Require representative evals for behavior and quality
  claims. Do not infer a defect merely from regex use, or add model calls to
  deterministic rendering when interpretation can happen once upstream.
- Types and APIs: construction, mutation and wire admission preserve
  invariants. Check optional values, defaulting, collection keys, identity
  and precision. Use existing domain or standard-library value types when
  they carry the invariant: a local clock is a `time`, not an encoded clock
  string. Convert provider encodings at the wire boundary. A cast or
  annotation does not validate external data.
- Ownership: borrowed versus copied values, justified allocation on hot
  paths, and owning scopes for files, connections, tasks and subscriptions.
  Cancellation must not close resources while in-flight work still uses them.
- Errors: recoverable failures propagate with their cause; absent or invalid
  data does not become a plausible value. Catch only what the boundary can
  handle; observe asynchronous failures; justify panics and unsafe operations.
- Evidence: tests exercise the production owner and can fail for its defect.
  Distinguish a feasible witness from an optimum, and a valid faster answer
  from a broken exact-time expectation. Do not propose weakening an oracle
  simply because the current implementation fails it. Performance claims
  require measurements of the real path.

Apply language-specific questions where relevant:

- Rust: ownership and borrowing, shared ownership, enum/trait design in
  context, error propagation, poison policy, unsafe safety obligations,
  and persisted-field defaults at the wire owner with missing-key coverage.
- Python: annotated function contracts, optional narrowing, mutable defaults,
  shared state, resource cleanup and third-party typing. Pydantic runtime
  validation is complementary to a static type checker. Check the actual
  checker configuration, import roots, plugins and stubs before claiming
  a call is checked. `Any`, excluded modules and suppressed errors limit
  coverage; framework-generated constructors need their supported integration.
- TypeScript: strict compiler and typed lint coverage, unchecked external
  data, promises, reactive dependencies and lifecycle cleanup. Preserve the
  framework's file conventions, aliases and component APIs. Assertions do
  not establish runtime shape.
