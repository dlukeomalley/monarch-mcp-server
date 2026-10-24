# Engineering

Use the eng-rig skill and shared standard before writing or reviewing code. This
checkout serves Fleet's Bogle integration; preserve its token-file isolation and
registered tool contracts. Read README.md for the standalone operator workflow.

Use Python3.12 and the locked environment. The existing formatters are Black and
isort; do not add another formatter. Cover application, library, tooling and
login bootstrap code with strict mypy. Tests deliberately exercise rejected shapes.
Managed eng-rig hooks are checked too, with their bytes owned by the pinned installer.

Run make check for the local/commit gate and make test for offline unit tests.
Tests use a null keyring backend and mocked provider calls. Never run login_setup.py
or finance mutation tools as a check. Auth tests use temporary token files and
fake credentials; do not read, replace or delete the operator's credentials.

Fix behavior with a native failing witness first. Review independently using the
installed language reviewer, then triage findings and repair surviving defects.
Keep upstream dependency typing limits and unreviewed code explicit. Do not add
first-party suppressions or replace concrete types with Any to make checks pass.
