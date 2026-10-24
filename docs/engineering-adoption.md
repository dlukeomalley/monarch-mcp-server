# Adopt engineering checks on the mounted source

Base528189d167ea59f497afdc0dc6a44296488bc4a4 is the actual branch mounted by Fleet,
not fork main. Work from this source without merging upstream or changing the
runtime checkout until the candidate passes. The initial tree is clean. Fleet's
registry and auth owner resolve ~/git/external/monarch-mcp-server for Bogle.

Use the existing Python3.12 locked uv environment, Black, isort, mypy and pytest.
The baseline unit suite passes62 cases with a null keyring backend and mocked
provider calls. Strict mypy over src and login_setup.py finds five errors: the
unstubbed monarchmoney dependency at two imports, an unused optional backend probe,
and the unannotated bootstrap main plus its call. The server also has a preexisting
import suppression and legacy Any payload annotations; no complete typing claim.

Install the pinned eng-rig kit and native local/commit checks. Default discovery
must include all first-party source, bootstrap/tooling and managed hooks, while
omitting tests, environments, build outputs and linked checkout snapshots. Keep
the existing formatters off managed copies, whose canonical owner uses Ruff.
Document the actual third-party stub limit rather than suppressing first-party
errors. Remove the unused MonarchConfig model and inert optional-backend probe;
neither has a real application consumer. A generic async bridge can preserve its
concrete result type without changing tool behavior.

Authentication review finds a separate realm risk: when a fleet token is absent,
get_monarch_client can still fall through to environment credentials. Reproduce
that path using a temporary missing/empty token file and mocked login, then retain
the existing token-file-only contract. No real login, provider or keyring write.
Review the plan independently before implementation and keep findings/coverage
and upstream inference limits explicit. Broader payload/envelope consolidation
remains a separate review outcome, not a claim made by a green mypy run.

## Review coverage and findings

The independent language/ownership pass read all four application/bootstrap Python
files, all application tests and fixtures, the compiler conformance case, project
configuration and this design. Supporting reads covered the locked client's login,
MFA and persistence implementation, Fleet's registry/auth owner and Bogle persona.
The native eng-rig committed-source report at d5a7378 completed with full reads of
all seven requested application/auth/compiler files, plus supporting gate config.
It read AGENTS.md and CLAUDE.md, ran no checks (one denied tool), and did not read
the original tool tests, conftest or README; the separate independent pass did.
Managed hooks retain canonical provenance; this is not a fresh full audit of the
shared kit or its optional JavaScript asset. There is no application Rust or
TypeScript in this checkout.

| Finding | Witness and disposition |
| --- | --- |
| M1: token truncation and late permissions | Actual file-store tests fail for an old reader observing replacement bytes and for failed publication losing the old token. Same-directory owner-only temporary file, fsync and replace now preserve the previous file until publication. |
| M2: parallel insecure persistence | Password, environment-login and MFA witnesses expose saved-session defaults or explicit pickle writes. Both login calls disable library loading/saving; MFA uses the single secure publisher. |
| M3: false completion | Missing/blank/non-string tokens, failed persistence and managed-bootstrap witnesses fail before correction. The owner rejects unusable tokens and managed writes; bootstrap exits1 on failure and reports completion only after publication. |
| M4: inconsistent recovery | SSO/manual verification failures use the one deployment-aware recovery hint. Removed stale method-specific token recipes and account-data printing; retained existing nonempty-object admission, with None/list/empty-object failing witnesses. |
| M5: duplicate debug door | Repository/Fleet callers use the broader check_auth_status tool. Removed debug_session_loading and its duplicate store reasoning; native broad-door tests verify the managed token and absence of provider calls when missing. |
| Realm isolation | Missing/empty/wrong-key managed-file witnesses previously fell through to environment login. Managed deployments now read only their supplied file. |
| Backend capability and shadow state | Native priority/reselection witnesses replace backend-name guesses, startup writes and cached capability. The selected backend owns its capability; an empty keyring still permits the existing standalone file fallback. |
| Cancellation and orphan APIs | The native store-spy witness observed deletion before cancellation. Setup now preserves the previous session until replacement; delete_token and its sole helper lost their only application caller and were deleted. |
| Unused configuration | MonarchConfig had no application consumer. Removed it and its imports rather than retaining a test-only model. |
| F1: unrelated launch-directory deletion | The native reviewer identified obsolete relative-path cleanup. A temporary-home publisher actually deleted unrelated monarch_session.json before correction. No producer remains, so removed the cleanup and both calls. |
| F2: stale parallel fallback | A native fake-keyring witness retained the superseded plaintext token after successful publication. The secure owner now removes only its own fallback file after keyring success; cleanup errors propagate rather than silently creating another store. |
| F3: incomplete coroutine cleanup | A native bridge witness left an async generator open. asyncio.run inside the existing worker owns loop shutdown and closes it before returning, while retaining concrete static result inference. |

Backend capability follows the [keyring backend contract](https://keyring.readthedocs.io/en/latest/#write-your-own-keyring-backend)
and was checked against the locked implementation. Tests use fake backends,
credentials, provider clients and temporary homes/token files. No operator
credential operation or live finance call forms part of verification.

## Gate scope and remaining limits

Strict mypy discovers the four application/bootstrap files and three managed hook
files. The compiler witness checks real run_async result inference, required
annotations, function bodies, returning Any and typed Pydantic constructors,
model_construct and required/extra arguments. Native tests are excluded from
application mypy because they deliberately supply invalid shapes; their compiler
checks run in make typecheck. Build outputs, environments and linked worktree
snapshots are excluded. Black/isort omit only the three pinned managed hook files,
whose canonical formatter is Ruff; future first-party hook code is not excluded.

The monarchmoney override is solely for the locked third-party client's missing
stubs/py.typed marker. Its dynamically inferred methods and payloads remain a real
static limit. Existing first-party Any payload annotations and manual response
formatting are not a complete typed-model boundary. Remaining review work includes
provider response models, broad auth-check reply admission, pagination/completeness,
money/date validation and mutation-result truth. No first-party suppression or
additional Any annotation was introduced to make the gate pass.

Native-review F4 (repeated tool coroutine/render/error pipelines) and F5 (duplicated
TLS bootstrap/credential prompts) remain consolidation work. F6 (empty-account
refresh semantics) is unresolved; no provider mutation was run and no empty-list
behavior was invented. The report suggested a cleanup helper and separate error
policies only where evidence establishes their contracts; a shared function alone
would not resolve the legacy untyped response admission.

Verification at7ee851145f8e: make check and every normal commit hook pass, including
seven mypy sources, compiler conformance and100 offline tests. The installed native
correction report ioyidu33 completes with no confirmed surviving correction finding:
full secure-session owner, partial bridge/tests and evidence delta; one denied tool,
no executed checks. Its unconfirmed keyring-dependency question is resolved by the
existing required project dependency. The separate independent correction pass
fully reads the secure owner and both changed test files, with complete bridge/delta
coverage. Whole-server coverage comes from the prior full pass, not the final delta
report. Executor-submission failure before starting a coroutine remains uncovered;
the generator witness proves normal worker shutdown, not every startup failure.

File publication assumes a trusted standalone home and does not claim full
power-loss durability, symlink confinement or cross-store transactional rotation.
An explicitly empty MONARCH_TOKEN_FILE retains its existing standalone semantics;
admission of that deployment setting has not been reviewed. Old arbitrary
launch-directory session files are deliberately left to their owners.

Adoption applies to the actual mounted feature branch, not an unrelated fork main.
A reviewed commit and clean active-checkout fast-forward are required before
claiming runtime source adoption; already-running MCP processes may still require
their normal session restart. Nothing here changes authentication on the host.
