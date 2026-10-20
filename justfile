# Fixed local developer commands. Does not execute project TOML instructions.
default:
    @just --list

status:
    python3 -B scripts/development_interface.py assistant-hub status

context:
    python3 -B scripts/development_interface.py assistant-hub context

doctor:
    python3 -B scripts/development_interface.py assistant-hub doctor
    PYTHONPATH=src python3 -B -m assistant_hub doctor

docs-check:
    python3 -B scripts/development_interface.py assistant-hub docs-check

# Full local developer gate; GitHub's Python version matrix and published
# offline UI CI remain independently mandatory on the exact PR head.
verify: docs-check
    PYTHONPATH=src python3 -B -m unittest discover -s tests -v
    python3 -B -m compileall -q src tests scripts
    PYTHONPATH=src python3 -B -m assistant_hub doctor
    python3 -B scripts/check_public_tree.py --include-untracked
    python3 -B scripts/development_interface.py assistant-hub ui-check
