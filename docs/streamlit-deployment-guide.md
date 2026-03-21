# Deployment Guide

This document covers how to deploy the Ami application publicly:
- **Frontend** (Streamlit) -> Streamlit Community Cloud
- **Backend** (FastAPI) -> Azure Container Apps

Azure Container Apps is the recommended backend target for this project because it provides:
- external HTTPS ingress
- HTTP-based autoscaling across replicas
- better multi-user behavior than a single Azure Container Instance

---

## Prerequisites

- Repo pushed to GitHub (`https://github.com/micocomia/Ami`)
- API keys ready (from `backend/.env`)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Azure account with active subscription

---

## Part 1: Frontend — Streamlit Community Cloud

Streamlit Community Cloud deploys directly from GitHub.

### Step 1: Deploy the app

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **New app**
4. Select repository: `micocomia/Ami`
5. Set main file path: `frontend/main.py`
6. Click **Deploy**

Streamlit builds and hosts the app automatically. Any future `git push` to the connected branch triggers an automatic redeploy.

### Step 2: Set the backend URLs in app secrets

Once the backend is deployed (Part 2), set the backend URLs in **Streamlit Community Cloud app secrets** instead of hardcoding them in `frontend/config.py`.

Open your Streamlit app settings and add:

```toml
BACKEND_ENDPOINT = "https://<your-container-app-fqdn>/"
BACKEND_PUBLIC_ENDPOINT = "https://<your-container-app-fqdn>/"
```

Use:
- `BACKEND_ENDPOINT` for Streamlit server-side API calls
- `BACKEND_PUBLIC_ENDPOINT` for browser-facing media URLs (audio, diagrams, static assets)

`frontend/config.py` already reads these values from environment variables, so no code change is required.

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

## Part 2: Backend — Azure Container Apps

Azure Container Apps runs your FastAPI container behind a managed HTTPS endpoint and can scale to multiple replicas when request concurrency rises.

The backend requires four Azure services to run:

| Service | Purpose | Resources created |
|---|---|---|
| **Azure AI Search** | Vector store for RAG | 2 indexes: `ami-verified-content`, `ami-web-results` |
| **Azure Cosmos DB** | User data persistence | 1 database: `ami-userdata` with 8 containers (auto-created) |
| **Azure Blob Storage** | Audio, diagrams, manifests | 3 containers: `ami-audio`, `ami-diagrams`, `ami-manifests` |
| **Azure AI Document Intelligence** | Parse PDFs/PPTX for indexing (pre-deploy only) | 1 resource (S0 SKU) |

### Step 1: Log in to Azure

```bash
az login
```

### Step 2: Install / upgrade required Azure CLI support

```bash
az extension add --name containerapp --upgrade
```

### Step 3: Register required namespaces

```bash
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.Search
az provider register --namespace Microsoft.DocumentDB
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.CognitiveServices
```

Check until each shows `Registered`:

```bash
az provider show --namespace Microsoft.App --query registrationState -o tsv
az provider show --namespace Microsoft.OperationalInsights --query registrationState -o tsv
az provider show --namespace Microsoft.ContainerRegistry --query registrationState -o tsv
az provider show --namespace Microsoft.Search --query registrationState -o tsv
az provider show --namespace Microsoft.DocumentDB --query registrationState -o tsv
az provider show --namespace Microsoft.Storage --query registrationState -o tsv
az provider show --namespace Microsoft.CognitiveServices --query registrationState -o tsv
```

### Step 4: Create a resource group

```bash
az group create --name ami-rg --location eastus
```

### Step 5: Create a container registry

```bash
az acr create --resource-group ami-rg --name amiregistry --sku Basic --admin-enabled true
```

> **No free tier:** Azure Container Registry has no free tier. `Basic` (~$5/month) is the lowest available SKU.

### Step 6: Create Azure AI Search

```bash
az search service create \
  --resource-group ami-rg \
  --name ami-dti5902-search \
  --sku free \
  --location eastus
```

> **Free tier limits:** 50 MB total storage, 3 indexes max (Ami uses 2 ✓), shared infrastructure, no SLA. The service may be automatically deleted after extended inactivity. Upgrade to `--sku basic` or higher for production.

Retrieve the admin key:

```bash
az search admin-key show \
  --resource-group ami-rg \
  --service-name ami-dti5902-search \
  --query primaryKey -o tsv
```

Search endpoint:

```text
https://ami-dti5902-search.search.windows.net
```

### Step 7: Create Azure Cosmos DB

```bash
az cosmosdb create \
  --resource-group ami-rg \
  --name ami-dti5902-cosmos \
  --kind GlobalDocumentDB \
  --locations regionName=eastus isZoneRedundant=false \
  --default-consistency-level Session \
  --enable-free-tier true
```

> **Free tier:** 1,000 RU/s + 25 GB storage, lifetime free. Only one free-tier Cosmos DB account is allowed per Azure subscription. The backend provisions the `ami-userdata` database with 1,000 RU/s shared throughput so all 8 containers share the budget without exceeding the free tier.

Retrieve the connection string:

```bash
az cosmosdb keys list \
  --resource-group ami-rg \
  --name ami-dti5902-cosmos \
  --type connection-strings \
  --query "connectionStrings[0].connectionString" -o tsv
```

### Step 8: Create Azure Blob Storage

```bash
az storage account create \
  --resource-group ami-rg \
  --name amidti5902storage \
  --location eastus \
  --sku Standard_LRS
```

> **No CLI free-tier flag:** Azure's always-free tier includes 5 GB Blob Storage (LRS) + 15 GB egress/month automatically — no special flag needed. `Standard_LRS` is already the lowest-cost SKU. Charges apply beyond those limits.

Retrieve the connection string:

```bash
az storage account show-connection-string \
  --resource-group ami-rg \
  --name amidti5902storage \
  --query connectionString -o tsv
```

### Step 9: Create Azure AI Document Intelligence

```bash
az cognitiveservices account create \
  --resource-group ami-rg \
  --name ami-dti5902-document-intelligence \
  --kind FormRecognizer \
  --sku F0 \
  --location eastus \
  --yes
```

> **Free tier limits (F0):** 500 pages/month, 20 calls/minute, 4 MB file size limit. Suitable for pre-indexing a small course content library. If your `resources/verified-course-content/` folder grows large, upgrade to `--sku S0`.

Retrieve the endpoint and key:

```bash
az cognitiveservices account show \
  --resource-group ami-rg \
  --name ami-dti5902-document-intelligence \
  --query properties.endpoint -o tsv

az cognitiveservices account keys list \
  --resource-group ami-rg \
  --name ami-dti5902-document-intelligence \
  --query key1 -o tsv
```

### Step 10: Pre-index verified course content

Run the indexing script locally before building the Docker image. The script:
1. Uploads files from `resources/verified-course-content/` to Blob Storage
2. Calls Azure AI Document Intelligence to parse PDFs and PPTX files
3. Embeds and indexes content into Azure AI Search
4. Saves a snapshot hash to `ami-manifests`

Ensure `backend/.env` has the required Azure variables, then run:

```bash
conda activate ami-backend
cd backend
python scripts/preindex_verified_content.py
```

Optional re-index without re-uploading:

```bash
python scripts/preindex_verified_content.py --skip-upload
```

### Step 11: Build the backend image locally

The backend Docker image now defaults to `UVICORN_WORKERS=2`, which improves in-container request concurrency. This can be overridden at deployment time.

Build for `linux/amd64`:

```bash
docker build --platform linux/amd64 \
  -f ./backend/docker/Dockerfile \
  ./backend \
  -t amiregistry.azurecr.io/ami-backend:latest
```

### Step 12: Push the image to ACR

```bash
az acr login --name amiregistry
docker push amiregistry.azurecr.io/ami-backend:latest
```

### Step 13: Create a Container Apps environment

```bash
az containerapp env create \
  --name ami-env \
  --resource-group ami-rg \
  --location eastus
```

### Step 14: Deploy the backend to Azure Container Apps

This deployment shape targets the Azure Container Apps free tier:
- `UVICORN_WORKERS=2`
- `min replicas = 1`
- `max replicas = 3`
- `cpu=0.5`, `memory=1Gi` per replica
- HTTP scaling threshold = `1` concurrent request per replica

The low HTTP concurrency threshold is intentional because content generation is long-running and resource-heavy.

```bash
az containerapp create \
  --name ami-backend \
  --resource-group ami-rg \
  --environment ami-env \
  --image amiregistry.azurecr.io/ami-backend:latest \
  --ingress external \
  --target-port 8000 \
  --registry-server amiregistry.azurecr.io \
  --registry-username $(az acr credential show --name amiregistry --query username -o tsv) \
  --registry-password $(az acr credential show --name amiregistry --query "passwords[0].value" -o tsv) \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --scale-rule-name http-scale \
  --scale-rule-type http \
  --scale-rule-http-concurrency 1 \
  --secrets \
    openai-api-key=your_openai_key \
    jwt-secret=your_jwt_secret \
    serper-api-key=your_serper_key \
    brave-api-key=your_brave_key \
    azure-search-key=your_search_admin_key \
    azure-cosmos-conn='AccountEndpoint=https://ami-dti5902-cosmos.documents.azure.com:443/;AccountKey=your_key==' \
    azure-storage-conn='DefaultEndpointsProtocol=https;AccountName=amidti5902storage;AccountKey=your_key;EndpointSuffix=core.windows.net' \
    azure-di-key=your_di_key \
  --env-vars \
    OPENAI_API_KEY=secretref:openai-api-key \
    JWT_SECRET=secretref:jwt-secret \
    SERPER_API_KEY=secretref:serper-api-key \
    BRAVE_API_KEY=secretref:brave-api-key \
    AZURE_SEARCH_ENDPOINT=https://ami-dti5902-search.search.windows.net \
    AZURE_SEARCH_KEY=secretref:azure-search-key \
    AZURE_COSMOS_CONNECTION_STRING=secretref:azure-cosmos-conn \
    AZURE_STORAGE_CONNECTION_STRING=secretref:azure-storage-conn \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://ami-dti5902-document-intelligence.cognitiveservices.azure.com/ \
    AZURE_DOCUMENT_INTELLIGENCE_KEY=secretref:azure-di-key \
    UVICORN_WORKERS=2
```

### Step 15: Get the public backend URL

```bash
az containerapp show \
  --name ami-backend \
  --resource-group ami-rg \
  --query properties.configuration.ingress.fqdn -o tsv
```

Your backend will be available at:

```text
https://<returned-fqdn>/
```

API docs:

```text
https://<returned-fqdn>/docs
```

Use that same HTTPS base URL in Streamlit Community Cloud secrets for both:
- `BACKEND_ENDPOINT`
- `BACKEND_PUBLIC_ENDPOINT`

### Step 16: Verify deployment and inspect logs

Check the app:

```bash
az containerapp show \
  --name ami-backend \
  --resource-group ami-rg \
  --query properties.runningStatus -o tsv
```

View logs:

```bash
az containerapp logs show \
  --name ami-backend \
  --resource-group ami-rg \
  --follow
```

Common startup errors:
- `ValueError: AZURE_COSMOS_CONNECTION_STRING not set`
- `ValueError: AZURE_SEARCH_ENDPOINT not set`
- `ValueError: AZURE_STORAGE_CONNECTION_STRING not set`

---

## Scaling and concurrency tuning

This backend does long-running, LLM-heavy content generation. Start conservatively.

Recommended initial settings (free tier):
- `UVICORN_WORKERS=2`
- `cpu=0.5`
- `memory=1Gi`
- `min-replicas=1`
- `max-replicas=3`
- `http concurrency=1`

> **Free tier allocation:** 180,000 vCPU-seconds + 360,000 GiB-seconds per month. At 0.5 vCPU/1 GiB this supports roughly 100 hours of continuous single-replica runtime before incurring charges — adequate for development and low-traffic use.

If latency is still high under concurrent users:
- increase `max-replicas`
- keep HTTP concurrency low
- only increase `UVICORN_WORKERS` if replica memory headroom is healthy

Update the app later with:

```bash
az containerapp update \
  --name ami-backend \
  --resource-group ami-rg \
  --cpu 2 \
  --memory 4Gi \
  --min-replicas 1 \
  --max-replicas 8 \
  --set-env-vars UVICORN_WORKERS=3
```

---

## Redeployment (after code changes)

Rebuild and push the image:

```bash
docker build --platform linux/amd64 -f ./backend/docker/Dockerfile ./backend -t amiregistry.azurecr.io/ami-backend:latest
docker push amiregistry.azurecr.io/ami-backend:latest
```

Update the running app to the new image:

```bash
az containerapp update \
  --name ami-backend \
  --resource-group ami-rg \
  --image amiregistry.azurecr.io/ami-backend:latest
```

Frontend redeploys automatically on `git push` to GitHub.

---

## Re-indexing after adding new course content

Source files live in Blob Storage and the backend uses a snapshot hash to detect verified-content changes.

### Option A: Preindex script

Add new files to `resources/verified-course-content/<course>/<category>/`, then run:

```bash
conda activate ami-backend
cd backend
python scripts/preindex_verified_content.py
```

Optional:

```bash
python scripts/preindex_verified_content.py --skip-upload
```

### Option B: Manual upload

Upload new files directly to the `ami-course-content` container, then update the app revision so startup re-checks the snapshot:

```bash
az containerapp update \
  --name ami-backend \
  --resource-group ami-rg \
  --image amiregistry.azurecr.io/ami-backend:latest
```

Check logs for successful sync:

```bash
az containerapp logs show \
  --name ami-backend \
  --resource-group ami-rg
```

---

## Architecture Summary

```text
User Browser
    │
    ├──▶ Streamlit Community Cloud (frontend)
    │         frontend/main.py
    │         Auto-deploys from GitHub
    │
    └──▶ Azure Container Apps (backend)
              FastAPI on port 8000
              HTTPS ingress
              Multiple replicas via HTTP autoscaling
              Image stored in Azure Container Registry
              │
              ├──▶ Azure AI Search
              │         ami-verified-content
              │         ami-web-results
              │
              ├──▶ Azure Cosmos DB
              │         ami-userdata database
              │         runtime containers auto-created
              │
              └──▶ Azure Blob Storage
                        ami-audio
                        ami-diagrams
                        ami-manifests

Local machine (pre-deploy only)
    └──▶ Azure AI Document Intelligence
              Parses PDFs/PPTX -> Azure AI Search
```
