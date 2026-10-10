# AGENTS.md — sethucms-sdk-python

Python client SDK.

This repository is one part of SethuCMS. **Read `../sethucms/AGENTS.md` first** for the whole picture, the security rules that must not be broken, and the working agreements.

## Build and test

```sh
pip install -e ".[dev]" && python -m pytest
```

## Notes

Standard library only. Python 3.9 and newer.

## Always

- Run the tests for what you changed and say what you ran and what you could not run.
- Do not `git commit` or `git push` unless the owner asks.
- Never print or store a secret, token or password.
