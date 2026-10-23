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
2. Record the actions that the credential permits. Do not assume that a pull credential is read-only.
3. Create separate identities for runtime pulls and build pushes.
4. Add the new runtime identity to registry auth. Keep the old identity active.
5. Seal each credential for its target namespace. Validate each `SealedSecret` before you commit it.
6. Sync registry auth and the namespace-local `SealedSecret` first. Make sure that both runtime identities work.
7. Make sure that the canary namespace has the generated Secret. Then update the canary workload in a separate GitOps change.
8. Force a fresh image pull. Make sure that the pod starts and the application works.
9. If the canary fails, revert the workload change. Keep the old identity active during recovery.
10. Move the remaining consumers in small batches. Include scheduled jobs and build workflows.
11. Revoke the old identity after every required consumer uses and passes a fresh pull or push.

With htpasswd, each identity can pull, push, and delete in every repository. It does not provide read-only or repository-scoped permissions.
Record this limit. Plan a separate change for scoped registry authorization.

## Scan changes

- Run the repository pre-commit checks before you commit.
- Keep secret scanning enabled for every pull request. Scan both the current source tree and the pull request commit range.
- Allow known false positives only with a narrow rule and a clear reason.
- Do not disable a scan because old Git history contains a known exposure. Remove the value from current source and rotate it.

For a credential rotation, keep the old identity active until all required consumers use the new identities. Make sure that each namespace-local `SealedSecret` has produced its target `Secret` before changing a consumer. Record exposed historical credentials for separate remediation, even after removing them from the current tree.

A sealed manifest does not deploy unless an active Argo Application manages its path. Do not count an unmanaged manifest as a migrated consumer. Add Argo ownership before you rely on that Secret.

## Report an exposure

Do not add a credential, username, host name, namespace, or consumer list to a public issue. Report the impact and the remediation status without those details. Keep a private record of the full consumer inventory.
