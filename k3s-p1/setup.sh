curl -sfL https://get.k3s.io | sh -

sudo groupadd k3s
sudo usermod -aG k3s $USER

sudo chgrp k3s /etc/rancher/k3s/k3s.yaml
sudo chmod 640 /etc/rancher/k3s/k3s.yaml

newgrp k3s

kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
