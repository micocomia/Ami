# Backend of Ami

Ami is an AI-powered personalized learning platform that creates adaptive learning experiences tailored to individual learners' needs, skill gaps, and goals. The system combines advanced AI technologies including Large Language Models, Retrieval-Augmented Generation (RAG), and intelligent tutoring systems to deliver comprehensive educational content.

## Features

- **AI Chatbot Tutor**: Interactive conversational learning with personalized responses
- **Skill Gap Identification**: Analyzes learner profiles and identifies knowledge gaps
- **Learning Goal Refinement**: Helps learners define and refine their educational objectives
- **Adaptive Learner Modeling**: Creates and updates detailed learner profiles
- **Personalized Resource Delivery**: Generates tailored learning content and materials
- **Learning Path Scheduling**: Creates structured learning sequences with session planning
- **Knowledge Point Exploration**: Deep-dives into specific topics with multiple perspectives
- **Document Integration**: Combines various knowledge sources into cohesive learning materials
- **Quiz Generation**: Creates personalized assessments to test understanding

## Architecture

The system is built with a modular architecture consisting of:

- **Core Modules**:
  - `ai_chatbot_tutor`: Conversational AI tutoring interface
  - `skill_gap`: Analyzes and identifies learning gaps
  - `learner_profiler`: Manages learner profiles and adaptation
  - `learning_plan_generator`: Creates structured and adaptive learning plans
  - `content_generator`: Creates customized learning content
  - `learner_simulator`: Simulates learner behaviors for testing

- **Base Components**:
  - `llm_factory`: Manages different LLM providers (DeepSeek, OpenAI, etc.)
  - `rag_factory`: Handles retrieval-augmented generation
  - `embedder_factory`: Manages text embedding models
  - `searcher_factory`: Integrates web search capabilities

- **Configuration**: Hydra-based configuration management with YAML files

## Quickstart

### Option A: Docker (Recommended)

Docker lets you run the backend inside an isolated container so you don't need to install Python, manage dependencies, or worry about conflicts with other software on your computer. Think of it as a lightweight, self-contained package that has everything the backend needs to run.

#### Step 1 — Install Docker Desktop

Download and install **Docker Desktop** for your operating system:

| Operating System | Download Link |
|---|---|
| **Windows 10/11** | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| **macOS (Intel / Apple Silicon)** | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| **Linux (Ubuntu, Fedora, etc.)** | [Docker Desktop for Linux](https://docs.docker.com/desktop/setup/install/linux/) |

After installation, **open Docker Desktop** and wait until the whale icon in your system tray / menu bar shows a steady state (not "starting…"). Docker Desktop must be running whenever you want to start the backend.

> **Windows users:** Docker Desktop requires WSL 2 (Windows Subsystem for Linux). The installer will prompt you to enable it if it is not already turned on. Follow the on-screen instructions and restart your computer if asked.

#### Step 2 — Open a Terminal

You will run all commands below in a terminal (also called a command prompt or shell):

- **Windows:** Open **PowerShell** or **Command Prompt** (search for either in the Start menu).
- **macOS:** Open **Terminal** (found in Applications > Utilities, or search with Spotlight).
- **Linux:** Open your preferred terminal emulator.

Navigate to the `backend` folder of this project. For example, if you cloned the repository to your home directory:

```bash
cd path/to/5902Group5/backend
```

Replace `path/to/5902Group5/backend` with the actual path where you downloaded or cloned the project.

#### Step 3 — Set Up Your Environment Variables (API Keys)

The backend needs API keys to connect to AI services. These keys are stored in a file called `.env` that stays on your machine and is never uploaded to GitHub.

1. **Create your own `.env` file** by copying the provided example:

   ```bash
   cp .env.example .env
   ```

   > **Windows (Command Prompt):** Use `copy .env.example .env` instead.

2. **Open the new `.env` file** in any text editor (VS Code, Notepad, TextEdit, etc.).

3. **Replace the placeholder values** with your actual API keys. At a minimum you need **one** LLM provider key. For example, if you are using OpenAI:

   ```
   OPENAI_API_KEY=sk-abc123your-real-key-here
   ```

   Leave any keys you don't have as `...` — the backend will simply skip those providers.

4. **Set `JWT_SECRET`** to any random string (this secures user sessions). For example:

   ```
   JWT_SECRET=my-super-secret-random-string-12345
   ```

5. **Save and close** the file.

#### Step 4 — Build and Start the Backend

Run the following command from the `backend` folder:

```bash
docker compose -f docker/docker-compose.yml up --build
```

**What this does:**
- Downloads a base Python image (first time only).
- Installs all required Python libraries inside the container.
- Starts the backend server.

> **First run:** This may take **5–10 minutes** because it needs to download and install everything. You will see a lot of log output — this is normal. Subsequent starts are near-instant because Docker caches the work it already did.

When you see output similar to:

```
backend-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

the backend is ready.

#### Step 5 — Verify It Is Running

Open your web browser and go to:

```
http://localhost:8000/docs
```

You should see the **FastAPI automatic documentation page** listing all available endpoints. If you see this, the backend is running correctly.

#### Stopping the Backend

- **Option 1:** In the terminal where Docker is running, press `Ctrl+C`. This sends a stop signal to the container.
- **Option 2:** Open a new terminal and run:

  ```bash
  docker compose -f docker/docker-compose.yml down
  ```

Both options cleanly shut down the server. Your data (stored in the `data/users/` folder) is preserved between restarts.

#### Restarting After Stopping

To start the backend again, run the same command from Step 4:

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
| `port 8000 is already in use` | Another application is using port 8000. Stop that application, or change the port in `docker/docker-compose.yml` by editing `"8000:8000"` to e.g. `"5001:8000"` (then access the backend at `http://localhost:5001`). |
| Container starts but API calls fail | Check that your `.env` file has valid API keys. Open `.env` and verify the keys are filled in (not `...`). |
| Build fails with network errors | Check your internet connection. Docker needs to download packages during the first build. |
| `error during connect: … permission denied` (Linux) | Your user may not be in the `docker` group. Run `sudo usermod -aG docker $USER`, then log out and log back in. |

### Option B: Manual Setup (Conda)

**Prerequisites:**
- Python 3.13
- [Conda](https://docs.conda.io/en/latest/miniconda.html)

```bash
# 1. Create and activate a conda environment
conda create -n ami-backend python=3.13 -y
conda activate ami-backend

# 2. Install dependencies
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API keys, then start the server:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Core Learning Endpoints

#### Chat with AI Tutor

```bash
curl -X POST "http://localhost:8000/chat-with-tutor" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": "[{\"role\": \"user\", \"content\": \"Hello!\"}]",
    "learner_profile": "Learner profile information",
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

#### Refine Learning Goal

```bash
curl -X POST "http://localhost:8000/refine-learning-goal" \
  -H "Content-Type: application/json" \
  -d '{
    "learning_goal": "Learn machine learning",
    "learner_information": "Beginner with programming experience",
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

#### Identify Skill Gap (with learner info)

```bash
curl -X POST "http://localhost:8000/identify-skill-gap-with-info" \
  -H "Content-Type: application/json" \
  -d '{
    "learning_goal": "Learn data science",
    "learner_information": "Beginner with Python and statistics",
    "skill_requirements": "{\"required_skills\": [\"Python\", \"SQL\", \"Machine Learning\"]}",
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

#### Create Learner Profile

```bash
curl -X POST "http://localhost:8000/create-learner-profile-with-info" \
  -H "Content-Type: application/json" \
  -d '{
    "learning_goal": "Learn web development",
    "learner_information": "{\"experience\": \"beginner\", \"interests\": [\"frontend\", \"backend\"]}",
    "skill_gaps": "{\"missing_skills\": [\"JavaScript\", \"CSS\"]}",
    "method_name": "ami",
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

#### Schedule Learning Path

```bash
curl -X POST "http://localhost:8000/schedule-learning-path" \
  -H "Content-Type: application/json" \
  -d '{
    "learner_profile": "{\"skills\": [], \"goals\": [\"web development\"]}",
    "session_count": 10,
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

#### Generate Tailored Content

```bash
curl -X POST "http://localhost:8000/tailor-knowledge-content" \
  -H "Content-Type: application/json" \
  -d '{
    "learner_profile": "{\"level\": \"beginner\"}",
    "learning_path": "[{\"topic\": \"HTML Basics\"}]",
    "learning_session": "{\"current_topic\": \"HTML\"}",
    "use_search": true,
    "allow_parallel": true,
    "with_quiz": true
  }'
```

## Configuration

The application uses Hydra for configuration management. Key configuration files:

- `config/main.yaml`: Main application settings
- `config/default.yaml`: Default configurations for all modules
- Environment variables can override YAML settings

### LLM Configuration Guide

#### Setting Up LLM Providers

Ami supports multiple LLM providers. Configure them using environment variables or by modifying the configuration files:

**Environment Variables (Recommended for API Keys):**
```bash
# DeepSeek (default)
export DEEPSEEK_API_KEY="your-deepseek-api-key"

# OpenAI
export OPENAI_API_KEY="your-openai-api-key"

# Anthropic
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# Ollama (local)
export OLLAMA_BASE_URL="http://localhost:11434"
```

**Configuration File (`config/default.yaml`):**
```yaml
llm:
  provider: deepseek  # Options: deepseek, openai, anthropic, ollama
  model_name: deepseek-chat
  base_url: null      # Custom base URL for API endpoints
  temperature: 0      # Response randomness (0-1)
```

#### Available LLM Models

**DeepSeek Models:**
- `deepseek-chat` (default) - General purpose chat model
- `deepseek-coder` - Optimized for code generation and technical content

**OpenAI Models:**
- `gpt-4o` - Latest GPT-4 optimized model
- `gpt-4o-mini` - Cost-effective GPT-4 variant
- `gpt-3.5-turbo` - Fast and economical option

**Anthropic Models:**
- `claude-3-5-sonnet-20241022` - Latest Claude model (recommended)
- `claude-3-sonnet` - Balanced performance and speed
- `claude-3-haiku` - Fastest and most cost-effective

**Ollama Models (Local):**
- `llama2` - Meta's Llama 2
- `mistral` - Mistral AI model
- `codellama` - Code-optimized Llama variant

#### Model Selection Guidelines

**For Educational Content:**
- Use `deepseek-chat` or `claude-3-sonnet` for balanced quality and cost
- Use `gpt-4o` for premium content quality
- Use `deepseek-coder` for technical/programming topics

**For Code Generation:**
- `deepseek-coder` - Best for Chinese and English programming content
- `claude-3-5-sonnet` - Excellent for complex coding tasks
- `gpt-4o` - Reliable for general programming assistance

**For Cost Optimization:**
- `gpt-4o-mini` - Good performance at lower cost
- `claude-3-haiku` - Fast responses, minimal cost
- `deepseek-chat` - Competitive pricing with good quality

### Embedding Configuration

Configure text embedding models for RAG functionality:

```yaml
embedding:
  provider: huggingface
  model_name: sentence-transformers/all-mpnet-base-v2
  # Alternative models:
  # - sentence-transformers/all-MiniLM-L6-v2 (faster, lighter)
  # - text-embedding-ada-002 (OpenAI)
  # - text-embedding-3-small (OpenAI, newer)
```

### Search and RAG Configuration

**Web Search:**
```yaml
search:
  provider: duckduckgo  # Options: duckduckgo, serper, google
  max_results: 5
  loader_type: web
```

**Vector Store:**
```yaml
vectorstore:
  persist_directory: data/vectorstore   # runtime vectorstore
  collection_name: non-verified-content
```

**RAG Parameters:**
```yaml
rag:
  chunk_size: 1000          # Text chunk size for retrieval
  num_retrieval_results: 5  # Number of chunks to retrieve
  allow_parallel: true      # Enable parallel processing
  max_workers: 3           # Maximum parallel workers
```

### Server Configuration

```yaml
server:
  host: 127.0.0.1  # Bind address
  port: 8000       # Port number
```

### Environment-Specific Configuration

Create environment-specific configs by copying `config/main.yaml` to `config/prod.yaml` or `config/dev.yaml`:

```yaml
# config/prod.yaml
defaults:
  - default
  - _self_

debug: false
log_level: INFO

llm:
  provider: openai
  model_name: gpt-4o
  temperature: 0.1

server:
  host: 0.0.0.0
  port: 8080
```

Run with specific config:
```bash
python main.py --config-name=prod
```

### RAG and Search Configuration

The system supports multiple search providers:
- **DuckDuckGo**: Web search integration
- **ChromaDB**: Vector storage for document retrieval
- **Sentence Transformers**: Text embeddings

### Verified Course Content

The system supports loading and indexing verified course materials (lecture slides, syllabi, exercises, reference code) so the AI tutor can ground answers in trusted content.

**Directory structure:**

Place course folders under `resources/verified-course-content/`. Each folder follows the naming pattern:

```
{course_code}_{course-name}_{term}/
├── Syllabus/
├── Lectures/
├── Exercises/
└── References/
```

For example: `6.0001_introduction-to-computer-science-and-programming-in-python_fall-2016/`

**File naming — lecture numbers:**

Lecture files should contain `Lec_N` in the filename (e.g. `Lec_1.pdf`, `Lec_12.pdf`) so the system can automatically extract lecture numbers for metadata filtering. The following patterns are recognised:

- `Lec_1.pdf`
- `MIT11_437F16_Lec3.pdf`
- `MIT6_831S11_lec01.pdf`

**Supported file types:** `.pdf`, `.pptx`, `.json`, `.txt`, `.py`, `.md`

**Re-indexing:** On startup, the backend now compares a verified-content manifest against files in `resources/verified-course-content/` and automatically re-indexes when files are added, removed, or updated. Deleting `data/vectorstore/` still forces a full rebuild of all collections.

## Data Flow

1. **Learner Input**: CV upload, learning goals, or direct information
2. **Skill Analysis**: Identifies gaps between current skills and learning objectives
3. **Profile Creation**: Builds comprehensive learner profile with adaptive modeling
4. **Path Planning**: Generates personalized learning sequences
5. **Content Generation**: Creates tailored learning materials with optional quizzes
6. **Interactive Learning**: AI tutor provides conversational support throughout

## Development

### Project Structure

```
backend/
├── main.py                    # FastAPI application entry point
├── api_schemas.py            # Pydantic models for API requests
├── requirements.txt          # Python dependencies
├── docker/                    # Docker setup
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .dockerignore
├── config/                   # Configuration files
│   ├── main.yaml
│   ├── default.yaml
│   └── loader.py
├── base/                     # Core components and factories
│   ├── llm_factory.py
│   ├── rag_factory.py
│   ├── embedder_factory.py
│   └── search_rag.py
├── modules/                  # Feature modules
│   ├── ai_chatbot_tutor/
│   ├── skill_gap/
│   ├── learner_profiler/
│   ├── learning_plan_generator/
│   ├── content_generator/
│   └── learner_simulator/
└── utils/                    # Utility functions
    ├── preprocess.py
    └── llm_output.py
```

### Adding New Features

1. Create a new module under `modules/`
2. Define schemas in `modules/your_module/schemas.py`
3. Implement agents in `modules/your_module/agents/`
4. Add prompts in `modules/your_module/prompts/`
5. Register endpoints in `main.py`
6. Update API schemas in `api_schemas.py`

### Testing

Run tests from the `backend/` directory using:

```bash
python -m pytest tests
```

## Dependencies

Key dependencies include:
- **FastAPI**: Web framework
- **LangChain**: LLM orchestration
- **Hydra**: Configuration management
- **Pydantic**: Data validation
- **ChromaDB**: Vector database
- **Sentence Transformers**: Text embeddings
- **DuckDuckGo Search**: Web search

## Support

For issues and questions, please refer to the project documentation or create an issue in the repository.
