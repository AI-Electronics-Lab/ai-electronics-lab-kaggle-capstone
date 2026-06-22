# Code provenance

The initial deterministic circuit-modeling core and its focused tests were migrated from
the private production implementation through a file-level allowlist.

Before migration, every selected file passed:

1. source-commit verification;
2. regular-file and path-boundary checks;
3. secret, credential, private-path, private-network, and identifier scanning;
4. Python syntax compilation;
5. deterministic baseline tests;
6. SHA-256 manifest verification.

The migration did not transfer private Git history, operational data, production
configuration, deployment infrastructure, databases, logs, backups, generated artifacts,
or credentials.

The migrated code will be maintained and tested independently inside this capstone
repository.
