# Agent Change Ledger

**An inspectable, reversible file-editing boundary for human-supervised AI assistants.**

An assistant proposes JSON. A person reviews a diff. A small local runner checks file hashes, applies approved changes and records the originals. Undo refuses to overwrite subsequent human edits.

This is a working Python prototype, not an LLM, not a replacement for Claude and not a hardened security sandbox. It explores a narrower alternative to opaque agent edits: portable proposals, explicit approval and provenance independent of model vendor.

## Try it without a model

Python 3.10+, no dependencies. Run from this repository:

```sh
mkdir demo
printf '{"version":1,"changes":[{"path":"hello.txt","expected_sha256":null,"content":"Hello from a reviewed proposal!\\n"}]}' > proposal.json
python ledger.py --root demo preview proposal.json
python ledger.py --root demo apply proposal.json --approve
# Prints a journal path. To restore:
python ledger.py --root demo undo demo/.ledger/tx-REPLACE.json --approve
python -m unittest -v
```

For existing files, `expected_sha256` must equal the SHA-256 of the current bytes. `null` means the file must not exist. `content: null` deletes a file; a string supplies its complete UTF-8 replacement. New nested directories are created. Empty directories remain after undo.

## Optional: an actual local model with Ollama

Install [Ollama](https://github.com/ollama/ollama) from its official source, and obtain a model whose license and hardware requirements suit you. The adapter does not install software or download models. Ollama is MIT; each model has its own license. Do not select a cloud model if you require local-only inference.

```sh
python propose.py --root demo --model YOUR_INSTALLED_LOCAL_MODEL \
  --file hello.txt --instruction 'Make the greeting more concise' --output proposed.json
python ledger.py --root demo preview proposed.json
# Only after human review:
python ledger.py --root demo apply proposed.json --approve
```

The adapter contacts only `127.0.0.1:11434`, ignoring proxy variables. Only explicitly named files are included in the prompt. It does not execute model output. A valid output is checked against current hashes and saved exclusively, never overwriting an existing proposal. The model may propose other relative paths, so the complete diff must be reviewed.

**Validation status:** the deterministic editing core has been tested locally. Ollama was not installed in the development environment, so real model inference and model quality have **not** been verified. No benchmark against Claude or another assistant is claimed. The loopback endpoint alone does not prove that a separately configured model service is offline.

## Useful differences

- Proposals survive changing model providers; the runner is model-agnostic.
- No agent can silently bypass the CLI's explicit `--approve` argument through this interface.
- Stale plans are rejected before any write.
- Undo is itself a journaled transaction, not a blind overwrite.
- A synthetic partial-write failure is tested and compensated.
- Original contents are kept locally, never uploaded by the core.

## Boundaries that matter

Use this in a disposable working copy or a backed-up project, not production. It handles UTF-8 text only, up to 100 files and 1 MB per file. Paths escaping the root, symlinks and the `.ledger` directory are rejected. It does **not** execute shell commands.

The lock coordinates this tool's apply operations only. There remains a race with unrelated writers between checks and replacement. A malicious local process can circumvent these checks: this is **not** OS-level isolation. Hard links, unusual filesystems, external permission changes and abrupt process/power failures are not fully supported. A multi-file update is not globally atomic: individual files use atomic replacement, and ordinary caught failures attempt rollback. After a crash, inspect the prepared journal and lock manually before retrying. Journal files are trusted local records, not cryptographically signed; don't undo untrusted journals.

Journals contain **complete original contents**, potentially confidential. Keep `.ledger/` out of version control, protect the root, and do not use private documents for a public demo. Backups and proposal/model-output files are your responsibility. Existing POSIX file metadata is not preserved by replacement. The tool neither grants nor enforces broader user authorization; `--approve` means the human invoking it reviewed the proposal.

## Roadmap, not current capabilities

- File descriptor-based path handling to reduce symlink/race hazards.
- Verified crash recovery and a transaction-state inspector.
- Per-path allowlists and signed approval envelopes.
- Locally executed small-model integration tests and adversarial proposal fixtures.
- Model-independent evaluation: review time, conflict detection and recovery reliability.

These are concrete areas where more development and evaluation capacity would help. They do not require a particular paid AI subscription to function.

## Provenance

AI-assisted implementation. Uses standard-library SHA-256 preconditions, unified diffs, transaction journals and compensating edits, all established techniques. No claim of inventing these mechanisms. No proprietary code, model weights or user data are included. MIT license applies to this repository, not optional third-party runtimes/models.
