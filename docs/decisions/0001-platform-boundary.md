# 0001: Universal core, explicit provider boundary

Status: accepted for the initial pre-alpha scaffold.

Earlier isolated demos showed that provider and deployment concerns can obscure
the assistant's permission boundary. This repository starts with a universal
mechanism and synthetic fixture, without importing those demos or their data.

Core contracts describe capabilities, manifests, scoped events, poll results,
action intents, exact approval rules, and decisions. Trusted application code
explicitly registers adapters. Provider packages will translate those contracts;
the core will not discover or execute packages implicitly. No particular mail,
messaging, social, source-control, or device service defines the platform API.

Collection, planning, human review, and any future dispatch are separate concerns.
Only the first three exist here. Policy is deterministic and independent of an
LLM. Mutations require review by default, high risk always requires review, and
low-risk preapproval requires an exact explicitly approved rule.

Consequences: the scaffold is small and testable without network or dependencies,
but provides no real integrations or executable actions. Approval provenance,
production security, and provider conformance remain future work. Documentation
and tests must distinguish implemented behavior from these proposals.
