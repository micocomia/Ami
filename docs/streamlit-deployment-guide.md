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

Once the backend is deployed (Part 2), set the backend URLs in **Streamlit Community Cloud app secrets** instead of hardcoding them in `frontend/config.py`.

Open your Streamlit app settings and add:

```toml
BACKEND_ENDPOINT = "http://<your-container-dns>.eastus.azurecontainer.io:8000/"
BACKEND_PUBLIC_ENDPOINT = "http://<your-container-dns>.eastus.azurecontainer.io:8000/"
```

`frontend/config.py` already reads `BACKEND_ENDPOINT` and `BACKEND_PUBLIC_ENDPOINT` from environment variables, so no code change is required.

Use:
- `BACKEND_ENDPOINT` for Streamlit server-side API calls
- `BACKEND_PUBLIC_ENDPOINT` for browser-facing media URLs (audio, diagrams, static assets)

If you later place the backend behind a public HTTPS endpoint, update both values to that HTTPS URL.

Push to GitHub or restart the app from Community Cloud after updating secrets.

**Community Cloud + HTTP-only backends can break browser-loaded media.**
The Streamlit app itself can call an HTTP backend server-side, but audio/image/static URLs rendered into the browser use `BACKEND_PUBLIC_ENDPOINT`. If the frontend is served over HTTPS and `BACKEND_PUBLIC_ENDPOINT` is plain HTTP, browsers may block those media requests as mixed content.

If that happens:
- keep `BACKEND_ENDPOINT` pointed at the reachable backend origin for server-side API calls
- put the backend behind an HTTPS-capable public endpoint for `BACKEND_PUBLIC_ENDPOINT`

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

Opens a browser for authentication. Required before running any `az` commands.

### Step 2: Register required namespaces

Azure subscriptions need to explicitly opt in to each service namespace. Run all of these and wait for `"Registered"` before proceeding.

```bash
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.ContainerInstance
az provider register --namespace Microsoft.Search
az provider register --namespace Microsoft.DocumentDB
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.CognitiveServices

# Check status (repeat until "Registered")
az provider show --namespace Microsoft.ContainerRegistry --query registrationState
az provider show --namespace Microsoft.ContainerInstance --query registrationState
az provider show --namespace Microsoft.Search --query registrationState
az provider show --namespace Microsoft.DocumentDB --query registrationState
az provider show --namespace Microsoft.Storage --query registrationState
az provider show --namespace Microsoft.CognitiveServices --query registrationState
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

### Step 5: Create Azure AI Search

Azure AI Search is used as the vector store for RAG. The `standard` SKU is required for vector search support.

```bash
az search service create \
  --resource-group ami-rg \
  --name ami-dti5902-search \
  --sku standard \
  --location eastus
```

Retrieve the admin key — you'll need it as `AZURE_SEARCH_KEY`:

```bash
az search admin-key show --resource-group ami-rg --service-name ami-dti5902-search --query primaryKey -o tsv
```

The endpoint will be: `https://ami-dti5902-search.search.windows.net`

The two search indexes (`ami-verified-content`, `ami-web-results`) are created automatically the first time the backend runs.

### Step 6: Create Azure Cosmos DB

Cosmos DB stores all user data (accounts, goals, profiles, learning content, etc.).

```bash
az cosmosdb create \
  --resource-group ami-rg \
  --name ami-dti5902-cosmos \
  --kind GlobalDocumentDB \
  --locations regionName=eastus isZoneRedundant=false \
  --default-consistency-level Session
```

Retrieve the connection string — you'll need it as `AZURE_COSMOS_CONNECTION_STRING`:

```bash
az cosmosdb keys list \
  --resource-group ami-rg \
  --name ami-dti5902-cosmos \
  --type connection-strings \
  --query "connectionStrings[0].connectionString" -o tsv
```

The database (`ami-userdata`) and all 8 containers are created automatically the first time the backend connects.

### Step 7: Create Azure Blob Storage

Blob Storage holds generated audio files, diagrams, and content manifests.

```bash
az storage account create \
  --resource-group ami-rg \
  --name amidti5902storage \
  --location eastus \
  --sku Standard_LRS
```

Retrieve the connection string — you'll need it as `AZURE_STORAGE_CONNECTION_STRING`:

```bash
az storage account show-connection-string \
  --resource-group ami-rg \
  --name amidti5902storage \
  --query connectionString -o tsv
```

The three storage containers (`ami-audio`, `ami-diagrams`, `ami-manifests`) are created automatically on first use. A fourth container (`ami-course-content`) is created automatically when you run the preindex script in Step 9.

### Step 8: Create Azure AI Document Intelligence

Document Intelligence parses PDFs and PPTX files during pre-indexing. It is called from your local machine before deployment — the container itself does not need to call it at runtime once the index is populated.

```bash
az cognitiveservices account create \
  --resource-group ami-rg \
  --name ami-dti5902-document-intelligence \
  --kind FormRecognizer \
  --sku S0 \
  --location eastus \
  --yes
```

Retrieve the endpoint and key — you'll need them as `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY`:

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

### Step 9: Pre-index verified course content

Run the indexing script **locally** before building the Docker image. The script:
1. Uploads all PDFs/PPTX/JSON/text files from `resources/verified-course-content/` to the `ami-course-content` Blob Storage container
2. Calls Azure AI Document Intelligence to parse PDFs and PPTX files (via SAS URL — no local model needed)
3. Embeds and indexes everything into Azure AI Search
4. Saves a snapshot hash to `ami-manifests` so the container skips re-indexing if content is unchanged on startup

Ensure your `backend/.env` has all five Azure vars set, then:

```bash
conda activate ami-backend && cd backend
python scripts/preindex_verified_content.py
```

The script logs `Pre-index complete` when done. Confirm the `ami-verified-content` index and the `ami-course-content` blob container were created in the Azure portal before proceeding.

To re-index without re-uploading (if files are already in blob storage):

```bash
python scripts/preindex_verified_content.py --skip-upload
```

### Step 11: Build the Docker image locally

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

### Step 12: Push the image to ACR

Log in to ACR so Docker can authenticate, then push the image.

```bash
az acr login --name amiregistry
docker push amiregistry.azurecr.io/ami-backend:latest
```

This uploads all image layers to your private registry on Azure.

### Step 13: Deploy to Azure Container Instances

Creates and starts a container from your image. Replace all placeholder values with the actual keys collected in the steps above.

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
    OPENAI_API_KEY=your_openai_key \
    JWT_SECRET=your_jwt_secret \
    SERPER_API_KEY=your_serper_key \
    BRAVE_API_KEY=your_brave_key \
    AZURE_SEARCH_ENDPOINT=https://ami-search.search.windows.net \
    AZURE_SEARCH_KEY=your_search_admin_key \
    AZURE_COSMOS_CONNECTION_STRING="AccountEndpoint=https://ami-cosmos.documents.azure.com:443/;AccountKey=your_key==" \
    AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=amistorage;AccountKey=your_key;EndpointSuffix=core.windows.net" \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://ami-document-intelligence.cognitiveservices.azure.com/ \
    AZURE_DOCUMENT_INTELLIGENCE_KEY=your_di_key
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

**Environment variable reference:**
| Variable | Where to get it |
|---|---|
| `OPENAI_API_KEY` | platform.openai.com |
| `JWT_SECRET` | Any random secret string |
| `SERPER_API_KEY` | serper.dev |
| `BRAVE_API_KEY` | api.search.brave.com |
| `AZURE_SEARCH_ENDPOINT` | `https://ami-search.search.windows.net` |
| `AZURE_SEARCH_KEY` | Step 5 output |
| `AZURE_COSMOS_CONNECTION_STRING` | Step 6 output |
| `AZURE_STORAGE_CONNECTION_STRING` | Step 7 output |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Step 8 output |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Step 8 output |

Your backend will be available at:
```
http://ami-backend.eastus.azurecontainer.io:8000
```

API docs at:
```
http://ami-backend.eastus.azurecontainer.io:8000/docs
```

### Step 14: Verify the deployment

```bash
az container show --resource-group ami-rg --name ami-backend --query instanceView.state
```

Should return `"Running"`. If it shows `"Failed"`, check logs:

```bash
az container logs --resource-group ami-rg --name ami-backend
```

Common startup errors and their causes:
- `ValueError: AZURE_COSMOS_CONNECTION_STRING not set` — missing or malformed Cosmos connection string
- `ValueError: AZURE_SEARCH_ENDPOINT not set` — missing AI Search endpoint or key
- `ValueError: AZURE_STORAGE_CONNECTION_STRING not set` — missing Blob Storage connection string

---

## Re-indexing (after adding new course content)

Source files live in `ami-course-content` Blob Storage. The backend detects changes via a lightweight snapshot hash computed from blob metadata (name, etag, size, last-modified) — no file content reads required.

### Option A: Preindex script (upload new files + re-index)

Add new PDFs or PPTX files to `resources/verified-course-content/<course>/<category>/`, then run:

```bash
conda activate ami-backend && cd backend
python scripts/preindex_verified_content.py
```

This uploads the new files to `ami-course-content`, re-indexes everything into Azure AI Search, and updates the snapshot hash in `ami-manifests`. **A container restart is required** to pick up new content — the backend checks the snapshot hash at startup.

### Option B: Manual upload via Azure portal or CLI

Upload new files directly to the `ami-course-content` container under the correct path:
`{course_code}_{course_name}_{term}/{category}/{filename}`

Then restart the container. On startup, the backend detects the blob metadata has changed, clears the old index, and re-indexes automatically.

```bash
az container restart --resource-group ami-rg --name ami-backend
```

### Restarting the container

```bash
az container restart --resource-group ami-rg --name ami-backend
```

Check logs to confirm successful re-indexing:

```bash
az container logs --resource-group ami-rg --name ami-backend
# Look for: "Verified content sync completed"
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
              │
              ├──▶ Azure AI Search
              │         ami-verified-content (course RAG)
              │         ami-web-results (web search RAG)
              │
              ├──▶ Azure Cosmos DB
              │         ami-userdata database
              │         8 containers (auto-created)
              │
              └──▶ Azure Blob Storage
                        ami-audio
                        ami-diagrams
                        ami-manifests

Local machine (pre-deploy only)
    └──▶ Azure AI Document Intelligence
              Parses PDFs/PPTX → Azure AI Search (ami-verified-content)
              Manifest saved to Blob Storage (ami-manifests)
```
