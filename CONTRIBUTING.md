# Contributing

This pre-alpha accepts small, reviewable local changes with clear scope and test
evidence. Discuss substantial integrations and boundary changes first. There is
no selected license or general reuse grant yet; clarify rights with the owner
before redistributing or contributing third-party material.

Use Python 3.11+ and only the standard library at runtime and in tests. Running
from source with `PYTHONPATH=src` needs no installation. The optional package
build uses setuptools; building/installing is not part of offline verification.
Follow `AGENTS.md` for validation commands. Include behavior tests, inspect diffs,
and report actual checks and any failures. CI declares three Python versions;
do not claim a version was tested unless it ran.

Use synthetic fixtures only. Keep state outside the repo. Run the public-tree
check, review staged paths and content, and never commit secrets, sessions,
private messages, deployment configuration, or generated artifacts. A hygiene
check passing is not proof that a public tree contains no sensitive information.
