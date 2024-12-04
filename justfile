default:
  @just --list

seal-old:
    kubeseal -f private/minio-secret.yaml -w active/sealed-minio-secret.yaml --namespace minio-homelab --name minio-secret
    kubeseal -f private/minio-minio-secret.yaml -w minio/minio-minio-secret.yaml --namespace minio --name minio-secret
    kubeseal -f private/wyze-bridge-secret.yaml -w wyze-bridge/wyze-bridge-secret.yaml --namespace wyze-bridge --name wyze-bridge
    kubeseal -f private/play-outside-regcred.yaml -w play-outside/sealed-regcred.yaml
    kubeseal -f private/play-outside-secrets.yaml -w play-outside/sealed-play-outside-secrets.yaml
    kubeseal -f private/home-regcred.yaml -w home/sealed-regcred.yaml
    kubeseal -f private/regcred.yaml -w registry/sealed-regcred.yaml --namespace registry --name regcred
    kubeseal -f private/regcred.yaml -w installer/sealed-regcred.yaml --namespace installer --name regcred
    cat private/registry.password | kubeseal create secret --namespace registry --name registry.password
    cat private/registry.password | kubectl create secret generic registry-password --dry-run=client --from-file=htpasswd=/dev/stdin -o yaml > private/registry-password.yaml
    kubeseal -f private/registry-password.yaml -w registry/sealed-registry-password.yaml --namespace registry --name registry-password
    kubectl create configmap registry-config --dry-run=client --from-file=registry/config.yml -o yaml > registry/registry-config.yaml
    kubeseal < private/wyze-bridge-htpasswd-secret.yaml > wyze-bridge/htpasswd-sealed.yaml -o yaml
    kubeseal -f private/shots-secret.yaml -w shots/sealed-shots-secret.yaml --namespace shot --name minio-shots
    kubeseal -f private/basic-auth.yaml -w basic-auth/basic-auth-secret.yaml --namespace basic-auth --name basic-auth
    kubeseal -f private/reader.yaml -w reader/reader.yaml --namespace basic-auth --name basic-auth

seal name:
    kubeseal -f private/{{name}}.yaml -w {{name}}/{{name}}-sealed-secret.yaml --namespace {{name}} --name {{name}}-secret



argo-patch-insecure:
    kubectl patch configmap argocd-cmd-params-cm -n argocd --type merge -p '{"data":{"server.insecure":"true"}}'

forward: argo-echo-password argo-copy-password argo-forward

argo-forward:
    kubectl port-forward svc/argocd-server -n argocd 8080:443

argo-echo-password:
    #!/bin/bash
    echo -n 'admin password: '
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
argo-copy-password:
    #!/bin/bash
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d | xclip -selection clipboard
    echo 'password copied to clipboard'


