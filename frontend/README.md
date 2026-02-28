# Frontend of Ami

A Streamlit-based UI for Ami that guides learners through onboarding, goal refinement, skill-gaps analysis, learning-path scheduling, and in-session knowledge documents with quizzes. It talks to the Python backend over simple HTTP endpoints and can also run in a mock/offline mode using sample JSONs.

## Quickstart

### Option A: Docker (Recommended)

Docker lets you run the frontend inside an isolated container so you don't need to install Python, manage dependencies, or worry about conflicts with other software on your computer. Think of it as a lightweight, self-contained package that has everything the frontend needs to run.

#### Step 1 — Install Docker Desktop

Download and install **Docker Desktop** for your operating system:

| Operating System | Download Link |
|---|---|
| **Windows 10/11** | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| **macOS (Intel / Apple Silicon)** | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| **Linux (Ubuntu, Fedora, etc.)** | [Docker Desktop for Linux](https://docs.docker.com/desktop/setup/install/linux/) |

After installation, **open Docker Desktop** and wait until the whale icon in your system tray / menu bar shows a steady state (not "starting…"). Docker Desktop must be running whenever you want to start the frontend.

> **Windows users:** Docker Desktop requires WSL 2 (Windows Subsystem for Linux). The installer will prompt you to enable it if it is not already turned on. Follow the on-screen instructions and restart your computer if asked.

#### Step 2 — Open a Terminal

You will run all commands below in a terminal (also called a command prompt or shell):

- **Windows:** Open **PowerShell** or **Command Prompt** (search for either in the Start menu).
- **macOS:** Open **Terminal** (found in Applications > Utilities, or search with Spotlight).
- **Linux:** Open your preferred terminal emulator.

Navigate to the `frontend` folder of this project. For example, if you cloned the repository to your home directory:

```bash
cd path/to/5902Group5/frontend
```

Replace `path/to/5902Group5/frontend` with the actual path where you downloaded or cloned the project.

#### Step 3 — Make Sure the Backend Is Running

The frontend needs the backend server to be up so it can fetch data. Follow the instructions in `../backend/README.md` to start the backend first. By default the backend runs at `http://localhost:8000`.

> **Tip:** If you just want to explore the UI without a backend, you can skip this step and use **mock mode** instead. Open `config.py` and set `use_mock_data = True` before building the container.

#### Step 4 — Build and Start the Frontend

Run the following command from the `frontend` folder:

```bash
docker compose -f docker/docker-compose.yml up --build
```

**What this does:**
- Downloads a base Python image (first time only).
- Installs all required Python libraries inside the container.
- Starts the Streamlit frontend server.

> **First run:** This may take **5–10 minutes** because it needs to download and install everything. You will see a lot of log output — this is normal. Subsequent starts are near-instant because Docker caches the work it already did.

When you see output similar to:

```
frontend-1  |   You can now view your Streamlit app in your browser.
frontend-1  |
frontend-1  |   URL: http://0.0.0.0:8501
```

the frontend is ready.

#### Step 5 — Verify It Is Running

Open your web browser and go to:

```
http://localhost:8501
```

You should see the **Ami onboarding page**. If you see this, the frontend is running correctly.

#### Connecting to the Backend

By default the Docker container connects to the backend at `http://host.docker.internal:8000/` — this means a backend running on your host machine (outside Docker). If you need to point to a different backend, edit the `BACKEND_ENDPOINT` variable in `docker/docker-compose.yml`:

```yaml
environment:
  - BACKEND_ENDPOINT=http://your-backend-host:8000/
```

#### Stopping the Frontend

- **Option 1:** In the terminal where Docker is running, press `Ctrl+C`. This sends a stop signal to the container.
- **Option 2:** Open a new terminal and run:

  ```bash
  docker compose -f docker/docker-compose.yml down
  ```

Both options cleanly shut down the server.

#### Restarting After Stopping

To start the frontend again, run the same command from Step 4:

```bash
docker compose -f docker/docker-compose.yml up --build
```

> **Tip:** If you haven't changed any code since the last build, you can drop `--build` to start faster:
> ```bash
> docker compose -f docker/docker-compose.yml up
> ```

#### Rebuilding After Pulling New Code

Whenever you pull new changes from the repository (e.g., via `git pull`), rebuild the container so it picks up the updates:

```bash
git pull
docker compose -f docker/docker-compose.yml up --build
```

#### Troubleshooting

| Problem | Solution |
|---|---|
| `docker: command not found` | Docker Desktop is not installed, or its CLI tools are not on your PATH. Reinstall Docker Desktop and restart your terminal. On macOS, if Docker Desktop is installed but the command is still not found, add `export PATH="$HOME/.docker/bin:$PATH"` to your `~/.zshrc` file, then run `source ~/.zshrc` or open a new terminal. |
| `Cannot connect to the Docker daemon` | Docker Desktop is not running. Open the Docker Desktop application and wait for it to finish starting. |
| `port 8501 is already in use` | Another application is using port 8501. Stop that application, or change the port in `docker/docker-compose.yml` by editing `"8501:8501"` to e.g. `"8502:8501"` (then access the frontend at `http://localhost:8502`). |
| Backend 404/500 errors in the UI | Make sure the backend is running and `BACKEND_ENDPOINT` is correct in `docker/docker-compose.yml`. |
| Build fails with network errors | Check your internet connection. Docker needs to download packages during the first build. |
| `error during connect: … permission denied` (Linux) | Your user may not be in the `docker` group. Run `sudo usermod -aG docker $USER`, then log out and log back in. |

### Option B: Manual Setup (Conda)

**Prerequisites:**
- Python 3.13
- [Conda](https://docs.conda.io/en/latest/miniconda.html)

```bash
# 1. Create and activate a conda environment
conda create -n ami-frontend python=3.13 -y
conda activate ami-frontend

# 2. Install dependencies
cd frontend
pip install -r requirements.txt
```

Then launch the app:

```bash
# Run against a live backend (default)
#   Make sure the backend server is up (see ../backend)
streamlit run main.py

# Or run using mock data (no backend needed)
#   Edit config.py: set use_mock_data = True
streamlit run main.py
```

The app will open at <http://localhost:8501> by default.

## Configuration

All UI-related toggles live in `config.py`:

- `backend_endpoint`: Base URL for the backend API (default `http://127.0.0.1:8000/`). Can be overridden with the `BACKEND_ENDPOINT` environment variable.
- `use_mock_data`: When `True`, the UI serves sample data from `assets/data_example/` and does not call the backend.
- `use_search`: Allows knowledge drafting to use retrieval/search (sent to backend).

Update these as needed before launching. If you deploy the backend elsewhere, set `backend_endpoint` accordingly.

## Project structure

```text
frontend/
  main.py                 # Streamlit entry. Builds navigation and loads CSS/logo
  config.py               # Frontend configuration flags and API base URL
  requirements.txt        # Python dependencies (Streamlit + extras)
  .streamlit/config.toml  # Streamlit theme/layout defaults

  docker/                 # Docker setup
    Dockerfile
    docker-compose.yml
    .dockerignore

  assets/                 # Static assets and mock data
    css/                  # UI styles
    data_example/         # JSON fixtures for mock mode

  components/             # Reusable Streamlit components (chatbot, time tracking, etc.)
  pages/                  # Multi-page app: onboarding, learning path, knowledge document, dashboard, ...
  utils/                  # Helpers: API requests, formatting, PDF, state management, colors
```

Key pages:

- `pages/onboarding.py`: Collect learner info and set initial goal.
- `pages/learning_path.py`: View, (re)schedule, and navigate sessions.
- `pages/knowledge_document.py`: In-session reading experience with a document TOC, pagination, and quizzes.
- `pages/goal_management.py`: Manage/refine goals.
- `pages/dashboard.py`: Basic analytics overview.

## How it works

- UI state is stored in Streamlit `st.session_state`. Domain state is persisted through explicit backend resources such as goals, learning-content cache, session activity, runtime state, and dashboard metrics endpoints.
- Backend calls are made with `httpx` via `utils/request_api.py` using endpoints under `config.backend_endpoint`.
- When `use_mock_data=True`, the app reads JSON fixtures from `assets/data_example/` instead of calling the backend.
- The knowledge document page supports section-by-section pagination, a clickable sidebar TOC, and auto-scroll to anchors.

## Common tasks

- Switch to mock mode:

  1. Open `config.py`
  2. Set `use_mock_data = True`
  3. Run `streamlit run main.py`

- Point frontend to a remote backend:

  1. Open `config.py`
  2. Set `backend_endpoint = "http://<host>:<port>/"`

- Change default theme/layout:

  - Edit `.streamlit/config.toml` (e.g., theme colors, base font).

## Development tips

- Streamlit auto-reloads on file save. Keep logs visible in the terminal.
- Keep new code in `components/` when it's reusable, and page-specific logic under `pages/`.
- Prefer small, focused functions in `utils/` for API calls and formatting.
- Avoid heavy work on every rerun. Cache with `@st.cache_data` or `@st.cache_resource` when safe.

## License

This project is released under the repository's top-level license.
