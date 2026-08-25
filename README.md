# Microshop Microservices Lab

A small practice project for Docker, Kubernetes, Terraform, and Azure DevOps.

## Architecture

- `frontend` is the browser UI on port `8086` locally and proxies API calls.
- `/signin.html` is the customer sign-in and registration page; `/admin.html` is the separate admin workspace.
- `products` listens on port `8002` and owns the product catalog.
- `orders` listens on port `8000` and calls `inventory` to reserve stock.
- `inventory` listens on port `8001` and owns stock persistence.
- `payments` listens on port `8004` and provides sandbox payment authorization.
- Docker Compose runs all application services locally.
- Kubernetes manifests deploy all application services to AKS.
- Terraform provisions a resource group, ACR, AKS, and the ACR pull role.
- Azure Pipelines tests, scans, and deploys the five application images to AKS.
- Each service persists data in its own database; Docker volumes and Kubernetes PVCs preserve it.
- Prometheus scrapes service metrics and Grafana loads a starter dashboard.
- Auth service supports user and admin sign-in for the local practice workflow.
- Inventory publishes live stock changes over Server-Sent Events to the frontend.

## Run locally

Prerequisites: Docker Desktop with Compose.

```powershell
docker compose up --build
Start-Process http://localhost:8086
Invoke-RestMethod http://localhost:8002/products
Invoke-RestMethod -Uri http://localhost:8000/orders -Method Post -ContentType 'application/json' -Body '{"sku":"keyboard","quantity":2}'
Invoke-RestMethod http://localhost:8001/stock
```

Useful endpoints:

- Open `http://localhost:8086` for the frontend
- `GET /health` on each backend service
- `POST /payments/authorize` on payments authorizes a sandbox payment; use `declined` as the test payment reference to simulate failure
- `GET /products` on products
- `GET /stock` on inventory
- `POST /orders` with `{"sku":"keyboard","quantity":1}` on orders
- `POST /products` with `{"name":"USB Hub","category":"Desk","price":29.99}` creates a pending product
- `PUT /admin/products/<id>/enable` activates a product
- `GET /events` on products streams live catalog changes
- `POST /stock/enable` with `{"sku":"<id>","quantity":10}` enables starting stock
- `POST /stock/restock` with `{"sku":"<id>","quantity":10}` adds stock to a live product (admin only)
- `GET /metrics` on products, inventory, and orders exposes Prometheus metrics
- `GET /events` on inventory streams stock changes to connected clients
- `GET /events` on orders streams new order status snapshots to connected clients
- `GET /admin/orders` lists orders for administrators
- `PUT /admin/orders/<id>/status` with `{"status":"shipped"}` updates fulfillment status and broadcasts the change

## Metrics dashboard

Open Prometheus at `http://localhost:9091`, Grafana at `http://localhost:3002`, and Zipkin at `http://localhost:9412` after starting Compose with `docker compose -f docker-compose.yml -f docker-compose.override.yml.example up --build`. Grafana provisions the Microshop dashboard automatically; its first-run login is `admin` / `admin`.

## Sign in

Practice credentials are `user` / `user123` for ordering and `admin` / `admin123` for product submission, approval, and stock enablement. These credentials and the local HMAC secret are for practice only. Admin operations are also enforced by the backend, so direct API calls require the admin bearer token.

New users can register from the frontend. Registration creates a normal `user` account; admin access is intentionally limited to the seeded practice admin account.

## Provision Azure with Terraform

Authenticate first with `az login`, then run:

```powershell
cd infra/terraform
$env:TF_VAR_subscription_id = "<subscription-id>"
terraform init
terraform plan -var="registry_name=<globally-unique-acr-name>"
terraform apply -var="registry_name=<globally-unique-acr-name>"
```

The AKS node identity is granted `AcrPull`. Keep the generated `terraform.tfstate` private.

Products, inventory, and orders use separate service-owned SQLite databases. Local Docker volumes are named `practice_products-data`, `practice_inventory-data`, and `practice_orders-data`; Kubernetes uses the PVCs in `deploy/k8s/storage.yaml`. Payments is currently a sandbox service and should be replaced with a PCI-compliant provider before production use.

## Deploy manually to Kubernetes

Build and push the images, then substitute the image server and tag in the manifests under `deploy/k8s`:

Create the namespace and secret first. Never commit the real secret; `secrets.example.yaml` is only a template:

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl -n microshop create secret generic microshop-secrets --from-literal=auth-secret="<long-random-secret>"
```

```powershell
find deploy/k8s -type f ! -name 'secrets.example.yaml' -print0 | xargs -0 kubectl apply -n microshop -f
kubectl get pods -n microshop
kubectl get service frontend -n microshop
```

## Azure DevOps setup

Create pipeline variables or variable-group values for `ACR_LOGIN_SERVER`, `ACR_SERVICE_CONNECTION`, `AZURE_SERVICE_CONNECTION`, `AKS_RESOURCE_GROUP`, `AKS_NAME`, and `SONARQUBE_SERVICE_CONNECTION`. The pipeline runs API tests, a SonarQube quality gate, and Trivy HIGH/CRITICAL image scans before building the five images once and promoting the same immutable `Build.BuildId` tag through `Dev`, `QA`, `UAT`, and `Prod`. Create Azure DevOps environments named `microshop-dev`, `microshop-qa`, `microshop-uat`, and `microshop-prod`; configure approval checks on UAT and Prod.

## Cleanup

```powershell
cd infra/terraform
terraform destroy -var="registry_name=<globally-unique-acr-name>"
```

