default:
  @just --list

seal:
    kubeseal -f private/minio-secret.yaml -w active/sealed-minio-secret.yaml --namespace minio-homelab --name minio-secret
    kubeseal -f private/minio-minio-secret.yaml -w minio/minio-minio-secret.yaml --namespace minio --name minio-secret
    kubeseal -f private/play-outside-regcred.yaml -w play-outside/sealed-regcred.yaml
    kubeseal -f private/home-regcred.yaml -w home/sealed-regcred.yaml
    kubeseal -f private/regcred.yaml -w registry/sealed-regcred.yaml --namespace registry --name regcred
    cat private/registry.password | kubeseal create secret --namespace registry --name registry.password
    cat private/registry.password | kubectl create secret generic mysecret --dry-run=client --from-file=foo=/dev/stdin -o yaml > private/registry-password.yaml
    kubeseal -f private/registry-password.yaml -w registry/sealed-registry-password.yaml
