# ![Cover image](images/cover-3.png)

Test out with kind.

``` bash
kind create cluster --name minecraft
```

Install Argo

``` bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argo argo/argo-cd --namespace argocd --create-namespace
```

Go to the argocd dashboard.

``` bash
kubectl port-forward service/argo-argocd-server -n argocd 8080:443
argocd admin initial-password -n argocd
argocd login localhost:8080
argocd app list
```

Create an app

``` bash
argocd app create homelab --repo https://github.com/waylonwalker/homelab-argo --path active --dest-server https://kubernetes.default.svc --dest-namespace homelab
argocd app list
argocd app sync homelab
argocd app list
argocd app set homelab --sync-policy automated --auto-prune
argocd app list
argocd app get homelab
```
