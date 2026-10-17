# Security assumptions and limitations

This is not production software. It has no external dispatch, network access,
real credentials, authentication service, or language-model permission path.
Untrusted event text is data and cannot create approval rules or capabilities.
Rules must come from trusted application code after explicit user approval;
`approved_by` is a local claim, not cryptographic proof. Reviewers are likewise
caller-supplied labels. Do not expose this CLI as a multi-user service.

The registry is explicit enablement of trusted code, not a sandbox. A malicious
Python adapter could bypass core policy through its own code. Capability
manifests declare permission metadata; they do not prove adapter behavior.
Polling adapters must be read-only. Invalid or cross-scope events reject the
entire batch before cursor advancement. SQL values use bound parameters.

Database files use mode 0600 on the supported POSIX environment. The store rejects
symlink paths and nonregular files. New state directories request 0700; existing
parent directories are not repaired. SQLite rollback journals follow SQLite's
local-file behavior. The database and audit log are neither encrypted nor
tamper-evident. Filesystem owners can edit them. Path checks are not a defense
against hostile concurrent replacement in an attacker-controlled directory.
Use a trusted private directory. Backups and terminal output can expose content.

The audit log contains intent keys, decisions, collection counts, and review
labels. Intent payloads and event bodies are stored in plaintext. This scaffold
has no retention, export-redaction, or deletion policy. Use synthetic data only.
There is no account authorization model beyond adapter validation and caller
scope. Unknown capabilities deny; high-risk actions always require review,
including when an exact low-risk-style rule would otherwise match.

`.gitignore` and `scripts/check_public_tree.py` reduce accidental publication of
state and common key material. The script reads only Git-listed paths, rejects
symlinks before reading, bounds file sizes, and prints categories and paths rather
than matched content. It cannot detect every secret, private message, URL, or
sensitive fact. Review staged diffs manually. Never add real credentials,
sessions, personal messages, subscription links, or deployment access details.
