# Secret handling for GitOps

Use this guide when you add, move, or rotate a credential in this repository.

## Keep credentials out of source

- Do not commit a Kubernetes `Secret` with a real value. Base64 encoding does not protect a value.
- Store encrypted values in a strict-scope `SealedSecret`. Its name and namespace must match the target `Secret`.
- Do not put a password, token, private key, or encoded copy in a workflow file, example, log, or issue comment.
- Do not print credentials from build scripts. Read them from a protected file or standard input.
- Set local credential files to owner-only access. Remove temporary files after use.

## Rotate a credential

1. Find every workload, job, build script, and operator that uses the credential.
2. Check which actions the credential permits. Do not assume that a pull credential is read-only.
3. Create a new credential. Keep the old credential active during the canary.
4. Seal the new value for each target namespace. Validate each `SealedSecret` before you commit it.
5. Update one canary workload. Make it pull a fresh image, then check that it starts successfully.
6. Move the remaining consumers to the new credential. Check scheduled jobs and build tools as well.
7. Revoke the old credential after every consumer uses the new one.

If the service cannot limit permissions, record that limit. Use the credential only where needed. Plan a separate change to add scoped access.

## Scan changes

- Run the repository pre-commit checks before you commit.
- Keep secret scanning enabled for every pull request. Scan the current source tree.
- Allow known false positives only with a narrow rule and a clear reason.
- Do not disable a scan because old Git history contains a known exposure. Remove the value from current source and rotate it.

## Report an exposure

Do not add a credential, username, host name, namespace, or consumer list to a public issue. Report the impact and the remediation status without those details. Keep a private record of the full consumer inventory.
