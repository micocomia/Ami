# Deployment Guide

This document covers how to deploy the Ami application publicly:
- **Frontend** (Streamlit) → Streamlit Community Cloud
- **Backend** (FastAPI) → Azure Container Instances

---

## Prerequisites

- Repo pushed to GitHub (`https://github.com/micocomia/Ami`)
- API keys ready (from `backend/.env`)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Azure account with active subscription

---

## Part 1: Frontend — Streamlit Community Cloud

Streamlit Community Cloud is a free hosting platform by Streamlit that deploys directly from GitHub.

### Step 1: Deploy the app

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **New app**
4. Select repository: `micocomia/Ami`
5. Set main file path: `frontend/main.py`
6. Click **Deploy**

Streamlit builds and hosts the app automatically. Any future `git push` to the connected branch triggers an automatic redeploy.

### Step 2: Set the backend URL

Once the backend is deployed (Part 2), update `frontend/config.py`:

```python
BACKEND_ENDPOINT = "http://<your-container-dns>.eastus.azurecontainer.io:8000"
```

Push to GitHub — Streamlit redeploys automatically.

### Known Issues

**Relative file paths fail in Community Cloud.**
Community Cloud runs the app from a different working directory than local. Any `open('./assets/...')` or `st.image('./assets/...')` calls must use absolute paths:

```python
import os
path = os.path.join(os.path.dirname(__file__), "assets/css/main.css")
```

**Theme colors may not apply from `config.toml`.**
Community Cloud does not always pick up `[theme]` settings from `.streamlit/config.toml`. Apply theme colors explicitly in `frontend/assets/css/main.css` using CSS overrides targeting Streamlit's internal element selectors.

---

## Part 2: Backend — Azure Container Instances

Azure Container Instances (ACI) runs a Docker container directly without managing servers or clusters. The image is stored in Azure Container Registry (ACR).

### Step 1: Log in to Azure

```bash
az login
```

Opens a browser for authentication. Required before running any `az` commands.

### Step 2: Register required namespaces

Azure subscriptions need to explicitly opt in to each service namespace. Run both and wait for `"Registered"` before proceeding.

```bash
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.ContainerInstance

# Check status (repeat until "Registered")
az provider show --namespace Microsoft.ContainerRegistry --query registrationState
az provider show --namespace Microsoft.ContainerInstance --query registrationState
```

This typically takes 5-10 minutes per namespace.

### Step 3: Create a resource group

A resource group is a logical container for all Azure resources belonging to this project.

```bash
az group create --name ami-rg --location eastus
```

### Step 4: Create a container registry

Azure Container Registry (ACR) is a private Docker image registry hosted on Azure. The `--admin-enabled true` flag allows username/password authentication when pulling images during deployment.

```bash
az acr create --resource-group ami-rg --name amiregistry --sku Basic --admin-enabled true
```

### Step 5: Build the Docker image locally

Build the backend image for the `linux/amd64` platform. This is required because:
- Mac (Apple Silicon) builds ARM images by default
- Azure Container Instances requires AMD64

```bash
docker build --platform linux/amd64 \
  -f ./backend/docker/Dockerfile \
  ./backend \
  -t amiregistry.azurecr.io/ami-backend:latest
```

- `--platform linux/amd64` — forces AMD64 architecture
- `-f ./backend/docker/Dockerfile` — path to the Dockerfile (nested inside `docker/`)
- `./backend` — build context (files available during the build)
- `-t` — tags the image with the ACR registry URL

### Step 6: Push the image to ACR

Log in to ACR so Docker can authenticate, then push the image.

```bash
az acr login --name amiregistry
docker push amiregistry.azurecr.io/ami-backend:latest
```

This uploads all image layers to your private registry on Azure.

### Step 7: Deploy to Azure Container Instances

Creates and starts a container from your image. Replace all `your_key` values with actual keys from `backend/.env`.

```bash
az container create \
  --resource-group ami-rg \
  --name ami-backend \
  --image amiregistry.azurecr.io/ami-backend:latest \
  --registry-login-server amiregistry.azurecr.io \
  --registry-username $(az acr credential show --name amiregistry --query username -o tsv) \
  --registry-password $(az acr credential show --name amiregistry --query "passwords[0].value" -o tsv) \
  --dns-name-label ami-backend \
  --ports 8000 \
  --memory 4 \
  --cpu 2 \
  --os-type Linux \
  --environment-variables \
    OPENAI_API_KEY=your_key \
    JWT_SECRET=your_key \
    SERPER_API_KEY=your_key \
    BRAVE_API_KEY=your_key
```

**Parameter explanations:**
| Parameter | Purpose |
|---|---|
| `--image` | The Docker image to run from ACR |
| `--registry-*` | ACR credentials so Azure can pull the image |
| `--dns-name-label` | Creates a public URL: `ami-backend.eastus.azurecontainer.io` |
| `--ports 8000` | Exposes port 8000 (FastAPI default) |
| `--memory 4` | 4 GB RAM allocated to the container |
| `--cpu 2` | 2 CPU cores allocated |
| `--os-type Linux` | Required — must match the image OS |
| `--environment-variables` | Injects secrets as env vars (equivalent to `.env` file) |

Your backend will be available at:
```
http://ami-backend.eastus.azurecontainer.io:8000
```

API docs at:
```
http://ami-backend.eastus.azurecontainer.io:8000/docs
```

### Step 8: Verify the deployment

```bash
az container show --resource-group ami-rg --name ami-backend --query instanceView.state
```

Should return `"Running"`. If it shows `"Failed"`, check logs:

```bash
az container logs --resource-group ami-rg --name ami-backend
```

---

## Redeployment (after code changes)

When backend code changes, rebuild and push a new image, then restart the container:

```bash
# Rebuild and push
docker build --platform linux/amd64 -f ./backend/docker/Dockerfile ./backend -t amiregistry.azurecr.io/ami-backend:latest
docker push amiregistry.azurecr.io/ami-backend:latest

# Restart container to pull latest image
az container restart --resource-group ami-rg --name ami-backend
```

Frontend redeploys automatically on every `git push` to GitHub.

---

## Architecture Summary

```
User Browser
    │
    ├──▶ Streamlit Community Cloud (frontend)
    │         frontend/main.py
    │         Auto-deploys from GitHub
    │
    └──▶ Azure Container Instances (backend)
              FastAPI on port 8000
              Image stored in Azure Container Registry
              Env vars injected at container creation
```
