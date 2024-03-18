default:
  @just --list

seal:
    kubeseal -f private/minio-secret.yaml -w active/sealed-minio-secret.yaml --namespace minio-homelab --name minio-secret
    kubeseal -f private/play-outside-regcred.yaml -w play-outside/sealed-regcred.yaml
    kubeseal -f private/home-regcred.yaml -w home/sealed-regcred.yaml
