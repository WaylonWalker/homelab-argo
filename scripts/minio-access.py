#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer",
#     "copier>=8.0",
# ]
# ///

from copier import run_copy
from pathlib import Path
import secrets
import subprocess
import typer

app = typer.Typer()


@app.command()
def minio_access(
    name: str = typer.Option(..., help="The MinIO username and template name"),
    bucket: str = typer.Option(None, help="The MinIO bucket name. Defaults to name."),
    dir: str = typer.Option(None, help="Directory name. Defaults to name."),
):
    bucket = bucket or name
    target_dir = dir or name
    private_dir = Path("private") / target_dir
    access_dir = private_dir / "minio-access"
    policy_file = private_dir / "minio-rw-policy.json"
    access_json = private_dir / "minio-access.json"
    secret_yaml = private_dir / "minio-secret.yaml"
    sealed_secret_yaml = Path(target_dir) / "sealed-minio-secret.yaml"

    password = secrets.token_hex(32)
    typer.echo(f"USERNAME: {name}")
    typer.echo(f"PASSWORD: {password}")

    # Run copier using Python API
    run_copy(
        src_path="templates/minio",
        dst_path=private_dir,
        data={"name": bucket},
        overwrite=True,
    )

    # Create necessary directories
    access_dir.mkdir(parents=True, exist_ok=True)

    # Create MinIO policy and user
    subprocess.run(
        [
            "mcli",
            "admin",
            "policy",
            "create",
            "minio-wayl-one",
            f"{name}-readwrite",
            str(policy_file),
        ],
        check=True,
    )

    subprocess.run(
        ["mcli", "admin", "user", "add", "minio-wayl-one", name, password], check=True
    )

    subprocess.run(
        [
            "mcli",
            "admin",
            "policy",
            "attach",
            "minio-wayl-one",
            f"{name}-readwrite",
            "--user",
            name,
        ],
        check=True,
    )

    # Create service account and save credentials
    with open(access_json, "w") as f:
        subprocess.run(
            [
                "mcli",
                "admin",
                "user",
                "svcacct",
                "add",
                "minio-wayl-one",
                name,
                "--name",
                f"{name}-RW-Access",
                "--description",
                f"{name} Key for read write access",
                "--json",
            ],
            check=True,
            stdout=f,
        )

    # Generate Kubernetes secret YAML
    command = f"""
kubectl create secret generic {name}-minio-secret \
--namespace {name} \
--from-literal=AWS_ACCESS_KEY_ID=$(jq -r '.accessKey' {access_json}) \
--from-literal=AWS_SECRET_ACCESS_KEY=$(jq -r '.secretKey' {access_json}) \
--from-literal=AWS_BUCKET_NAME={bucket} \
--from-literal=AWS_BUCKET=s3://{bucket}/ \
--from-literal=AWS_ENDPOINT_URL=https://minio.wayl.one \
--from-literal=AWS_ENDPOINTS=https://minio.wayl.one \
--from-literal=AWS_REGION=us-east-1 \
--dry-run=client -o yaml
"""
    yaml_output = subprocess.check_output(command, shell=True, text=True)
    with open(secret_yaml, "w") as f:
        f.write(yaml_output)

    # Seal the secret
    subprocess.run(
        [
            "kubeseal",
            "-f",
            str(secret_yaml),
            "-w",
            str(sealed_secret_yaml),
            "--namespace",
            name,
            "--name",
            f"{name}-minio-secret",
        ],
        check=True,
    )


if __name__ == "__main__":
    app()
