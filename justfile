set dotenv-load

default:
  @just --list

seal-old:
    kubeseal -f private/minio-secret.yaml -w active/sealed-minio-secret.yaml --namespace minio-homelab --name minio-secret
    kubeseal -f private/minio-minio-secret.yaml -w minio/minio-minio-secret.yaml --namespace minio --name minio-secret
    kubeseal -f private/wyze-bridge-secret.yaml -w wyze-bridge/wyze-bridge-secret.yaml --namespace wyze-bridge --name wyze-bridge
    kubeseal -f private/play-outside-regcred.yaml -w play-outside/sealed-regcred.yaml
    kubeseal -f private/play-outside-secrets.yaml -w play-outside/sealed-play-outside-secrets.yaml
    kubeseal -f private/home-regcred.yaml -w home/sealed-regcred.yaml
    kubeseal -f private/regcred.yaml -w k8s/registry/sealed-regcred.yaml --namespace registry --name regcred
    kubeseal -f private/regcred.yaml -w installer/sealed-regcred.yaml --namespace installer --name regcred
    cat private/registry.password | kubeseal create secret --namespace registry --name registry.password
    cat private/registry.password | kubectl create secret generic registry-password --dry-run=client --from-file=htpasswd=/dev/stdin -o yaml > private/registry-password.yaml
    kubeseal -f private/registry-password.yaml -w k8s/registry/sealed-registry-password.yaml --namespace registry --name registry-password
    kubectl create configmap registry-config --dry-run=client --from-file=k8s/registry/config.yml -o yaml > k8s/registry/registry-config.yaml
    kubeseal < private/wyze-bridge-htpasswd-secret.yaml > wyze-bridge/htpasswd-sealed.yaml -o yaml
    kubeseal -f private/shots-secret.yaml -w shots/sealed-shots-secret.yaml --namespace shot --name minio-shots
    kubeseal -f private/basic-auth.yaml -w basic-auth/basic-auth-secret.yaml --namespace basic-auth --name basic-auth
    kubeseal -f private/reader.yaml -w reader/reader.yaml --namespace basic-auth --name basic-auth

seal name:
    #!/bin/bash
    set -euxo pipefail
    if [[ "{{name}}" == "all" ]]; then
        just seal-all
        exit 0
    fi
    git diff --cached --quiet
    kubeseal -f private/{{name}}.yaml -w {{name}}/{{name}}-sealed-secret.yaml --namespace {{name}} --name {{name}}-secret
    git add {{name}}/{{name}}-sealed-secret.yaml
    git commit -vm "seal {{name}}"

regcred name:
    #!/bin/bash
    set -euxo pipefail
    kubeseal -f private/regcred.yaml -w {{name}}/sealed-regcred.yaml --namespace {{name}} --name regcred

seal-all:
    #!/usr/bin/env bash
    set -euxo pipefail

    secrets="
    basic-auth
    minio
    play-outside
    reader
    shots
    "
    for secret in $secrets; do
        echo "sealing $secret"
        just seal $secret
    done

argo-patch-insecure:
    kubectl patch configmap argocd-cmd-params-cm -n argocd --type merge -p '{"data":{"server.insecure":"true"}}'

forward: argo-echo-password argo-copy-password argo-forward

argo-forward:
    kubectl port-forward svc/argocd-server -n argocd 8080:443

argo-password: argo-echo-password argo-copy-password

argo-echo-password:
    #!/bin/bash
    echo -n 'admin password: '
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
argo-copy-password:
    #!/bin/bash
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d | xclip -selection clipboard
    echo 'password copied to clipboard'

argo-workflows-token: argo-workflows-echo-token argo-workflows-copy-token

argo-workflows-echo-token:
    #!/bin/bash
    echo 'workflows token: '
    kubectl get secret waylon.service-account-token -o=jsonpath='{.data.token}' -n argo-workflows | base64 --decode | tr -d '\n' | xargs -I {} echo 'Bearer {}'; echo

argo-workflows-copy-token:
    #!/bin/bash
    kubectl get secret waylon.service-account-token -o=jsonpath='{.data.token}' -n argo-workflows | base64 --decode | tr -d '\n' | xargs -I {} echo 'Bearer {}' | xclip -selection clipboard
    echo 'token copied to clipboard'

argo-workflows-copy-token-reader:
    #!/bin/bash
    kubectl get secret reader.service-account-token -o=jsonpath='{.data.token}' -n reader | base64 --decode | tr -d '\n' | xargs -I {} echo 'Bearer {}' | xclip -selection clipboard
    echo 'token copied to clipboard'

play playbook='common':
    #!/bin/bash
    set -euxo pipefail
    ansible-playbook -i ansible/inventory.ini ansible/{{playbook}}.yaml --vault-password-file ansible/vault_password

edit-ansible-secret:
    #!/bin/bash
    set -euxo pipefail
    ansible-vault edit ansible/secrets.yml --vault-password-file ansible/vault_password

s3-ls:
    #!/bin/bash
    set -euxo pipefail
    aws s3 cp requirements.txt s3://my-test-bucket
    aws s3 ls s3://my-test-bucket

cloudflared-token:
    kubectl create secret generic cloudflared-token --from-file=token=private/cloudflared-token.txt --dry-run=client -o yaml > private/cloudflared-secret.yaml
    kubeseal -f private/cloudflared-secret.yaml -w cloudflared/cloudflared-sealed-secret.yaml --namespace cloudflared --name cloudflared-token


update-system-upgrade-controller:
    #!/bin/bash
    set -euxo pipefail
    curl -fsSL https://github.com/rancher/system-upgrade-controller/releases/latest/download/system-upgrade-controller.yaml > system-upgrade-controller/system-upgrade-controller.yaml
    curl -fsSL https://github.com/rancher/system-upgrade-controller/releases/latest/download/crd.yaml > system-upgrade-controller/crd.yaml

minio-access name:
    #!/usr/bin/env bash
    set -uexo pipefail
    NEWPASSWORD=`openssl rand -hex 32`
    echo USERNAME: {{name}}
    echo PASSWORD: $NEWPASSWORD

    copier copy templates/minio private/{{name}} -d name={{name}} --overwrite

    mkdir -p private/{{name}}
    mkdir -p private/{{name}}/minio-access

    mc admin policy create minio-wayl-one {{name}}-readwrite private/{{name}}/minio-rw-policy.json
    mc admin user add minio-wayl-one {{name}} $NEWPASSWORD
    mc admin policy attach minio-wayl-one {{name}}-readwrite --user {{name}}
    # mc config host add minio-wayl-one https://minio.wayl.one {{name}} $NEWPASSWORD
    mc admin user svcacct add                       \
    minio-wayl-one {{name}}                     \
    --name "{{name}}-RW-Access"                         \
    --description "{{name}} Key for read write access" \
    --json > private/{{name}}/minio-access.json
    kubectl create secret generic {{name}}-minio-secret \
    --namespace {{name}} \
    --from-literal=AWS_ACCESS_KEY_ID=$(jq -r '.accessKey' private/{{name}}/minio-access.json) \
    --from-literal=AWS_SECRET_ACCESS_KEY=$(jq -r '.secretKey' private/{{name}}/minio-access.json) \
    --from-literal=AWS_BUCKET_NAME={{name}} \
    --from-literal=AWS_ENDPOINT_URL=https://minio.wayl.one \
    --from-literal=AWS_REGION=us-east-1 \
    --dry-run=client -o yaml > private/{{name}}/minio-secret.yaml
    kubeseal -f private/{{name}}/minio-secret.yaml -w {{name}}/sealed-minio-secret.yaml --namespace {{name}} --name {{name}}-minio-secret

create-secret:
    kubectl create secret generic dropper-secret --from-env-file=.env -n dropper --dry-run=client -o yaml > ../homelab-argo/private/dropper.yaml

create-github-token namespace="argocd" name="git-creds":
    mkdir -p "private/{{namespace}}"
    mkdir -p "{{namespace}}"
    gh auth token | kubectl create secret generic {{name}} \
        --namespace={{namespace}} \
        --from-file=token=/dev/stdin \
        --dry-run=client \
        -o yaml > "private/{{namespace}}/{{name}}.yaml"
    kubeseal -f "private/{{namespace}}/{{name}}.yaml" \
        -w "{{namespace}}/sealed-{{name}}.yaml" \
        --namespace {{namespace}} \
        --name {{name}}
    @echo "Created sealed secret in {{namespace}}/sealed-{{name}}.yaml"

create-kustomization app:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if [ ! -d "{{app}}" ]; then
        echo "Error: Directory {{app}} does not exist"
        exit 1
    fi
    
    # Find kubernetes manifests
    manifests=$(find {{app}} -maxdepth 1 -name "*.yaml" ! -name "kustomization.yaml")
    
    # Create resources list
    resources=""
    for manifest in $manifests; do
        resources="${resources}  - $(basename $manifest)\n"
    done
    
    # Get current image and tag from deployment
    current_image=$(grep -o 'image: .*' {{app}}/deployment.yaml | cut -d: -f2- | xargs)
    image_name=$(echo $current_image | cut -d: -f1)
    image_tag=$(echo $current_image | cut -d: -f2)
    
    # Create kustomization.yaml
    cat > {{app}}/kustomization.yaml << EOF

create-redis name="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ ! "{{name}}" == "" ]]; then
    password=`openssl rand -hex 32`
    clean_name=`echo {{name}} | sed 's/-/_/g'`
    echo "REDIS_PASSWORD_${clean_name^^}=$password" >> private/redis/.env
    echo "REDIS_URL_${clean_name^^}=redis://${clean_name,,}:${password}@redis.svc.cluster.local:6379" >> private/redis/.env
    fi
    kubectl create secret generic redis-acl-secret --from-env-file=private/redis/.env -n redis --dry-run=client -o yaml > ../homelab-argo/private/redis/redis-acl-secret.yaml
    kubeseal -f private/redis/redis-acl-secret.yaml -w redis/sealed-redis-acl-secret.yaml --namespace redis --name redis-acl-secret
