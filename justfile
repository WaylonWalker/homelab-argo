default:
  @just --list

seal:
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
