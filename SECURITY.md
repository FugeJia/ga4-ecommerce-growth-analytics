# Security

Do not open a public issue with credentials or user-level exports. Revoke exposed credentials immediately through the provider. Use GitHub private vulnerability reporting when available, otherwise share a minimal reproduction without secrets with the repository owner.

The app is intended for local analysis. It has no authentication or multi-tenant isolation and should not be exposed with sensitive data. Uploaded experiment files are processed in the app process; no connector uploads them automatically. Public repository examples contain synthetic aggregates only.
