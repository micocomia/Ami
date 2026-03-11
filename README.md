<div align="center">
  <p align="center">
    <img src="assets/Logo.png" alt="Ami Logo" width="200"/>
  </p>
   <p><b>Ami: Adaptive Mentoring Intelligence</b></p>
  <p>A cognitive-style adaptive AI tutor built on GenMentor (WWW 2025)</p>
</div>

---

## Overview

Ami is an adaptive tutoring system that personalizes learning goals, learning paths, session content, quizzes, and tutoring support around each learner.

This repository started from [GenMentor](https://arxiv.org/pdf/2501.15749) (WWW 2025, Industry Track), but the current codebase extends that work into a fuller tutoring platform with persistent runtime state, verified-content grounding, adaptive learner modeling over time, and production-style backend/frontend integration.

The system is grounded in two pedagogical frameworks:

- **Felder-Silverman Learning Style Model (FSLSM)**: characterizes each learner across four dimensions (active/reflective, sensing/intuitive, visual/verbal, sequential/global) to shape content format and presentation
- **SOLO Taxonomy**: classifies cognitive complexity across five levels (pre-structural → extended abstract) to calibrate content difficulty and quiz depth

This repo contains:
- `backend/`: FastAPI backend for auth, goals/profiles, adaptive pipelines, tutoring runtime, analytics, and session prefetch
- `frontend/`: Streamlit frontend for onboarding, skill-gap analysis, learning paths, learning sessions, profiles, goals, and dashboard flows
- `frontend-react/`: React SPA for the Beta release, currently in active development

## Key Capabilities

- **Goal clarification and skill-gap analysis**: Ami can refine a vague goal into a clearer target, identify missing skills, and ground the analysis in verified course materials when available.
- **Adaptive learner modeling**: the learner profile is not fixed after onboarding. Cognitive status and FSLSM learning preferences can evolve based on edits, feedback, event history, tutoring interactions, and mastery outcomes.
- **Personalized learning paths and sessions**: Ami adapts session sequencing, structure, presentation style, and quiz difficulty using FSLSM and SOLO rather than serving the same lesson to every learner.
- **Multi-modal learning content**: generated sessions can include structured explanations, diagrams, external media, optional audio, and quizzes.
- **Tool-using tutor**: the tutor can ground answers in the current session, retrieve verified content, search the web when needed, surface media, and update learning preferences from strong signals.
- **Quality, safety, and analytics**: the backend includes explicit evaluation and bias-auditing layers, mastery checks, progress tracking, analytics, caching, and session prefetch.

## How Ami Works

| Stage | What the learner experiences | What the system does |
|---|---|---|
| Goal and skill gap | The learner gets a clearer goal statement and a list of missing skills | Goal parsing/refinement, optional verified-content retrieval, skill mapping, skill-gap evaluation, and bias audit |
| Learning path | The learner receives a personalized sequence of sessions | The scheduler generates a plan, applies FSLSM structural overrides, simulates feedback, and refines when needed |
| Learning session | The learner sees tailored lesson content, assets, and quizzes | The content pipeline explores knowledge points, drafts content, runs quality checks, enriches with media/narrative/audio when appropriate, and builds quizzes |
| Tutor support | The learner can ask follow-up questions during study | The tutor assembles tools at request time for session retrieval, verified-content lookup, web search, media search, and preference updates |
| Ongoing adaptation | Later sessions can feel different as the learner progresses | The learner profile updates through edits, event history, feedback, chatbot signals, and mastery results; downstream modules adapt accordingly |
| Runtime experience | Session transitions are faster and progress is tracked | The backend persists state, caches generated content, prefetches the next unlearned session, tracks mastery, and serves analytics |

## System Architecture

<div align="center">
  <p align="center">
    <img src="assets/g5-framework.png" alt="System Architecture" width="700" style="box-shadow: 0 8px 24px rgba(0,0,0,0.15); border-radius: 8px;"/>
  </p>
</div>

### Core Backend Modules

1. **`skill_gap`**

   Clarifies goals, identifies skill gaps, retrieves supporting context when available, and audits the result for bias.

2. **`learner_profiler`**

   Creates and updates learner profiles, including cognitive status, FSLSM learning preferences, and profile adaptation over time.

3. **`learning_plan_generator`**

   Builds personalized learning paths, simulates learner feedback on those plans, and refines them when quality is not high enough.

4. **`content_generator`**

   Generates learning content through a staged pipeline with draft evaluation, integration checks, FSLSM-aware adaptation, media/audio enrichment, and quiz generation.

5. **`ai_chatbot_tutor`**

   Runs the conversational tutor ("Ami") with request-time tool assembly, grounded retrieval, and signal-gated learning preference updates.

### Runtime Services (Backend)

- Goal runtime-state computation
- Learning-content caching and prefetch (`services/content_prefetch.py`)
- Session activity and completion tracking
- Mastery evaluation and session mastery status
- Behavioral and dashboard analytics

## Ami vs. GenMentor

Ami started from [GenMentor](https://github.com/GeminiLight/gen-mentor), but the current project is substantially broader in scope.

- **Platform backend, not just generation endpoints**: Ami adds authentication, persistent goals, session runtime state, mastery tracking, analytics, caching, and prefetch.
- **Adaptive learner model over time**: Ami continuously updates cognitive status and FSLSM preferences, then uses those updates to adapt later plans, content, quizzes, and tutoring behavior.
- **Verified-content and tool-based grounding**: Ami adds verified-course-content retrieval and a tutor that can assemble tools at request time.
- **Richer delivery formats**: Ami supports diagrams, media enrichment, optional audio, and SOLO-aligned quizzes.
- **Explicit quality and bias controls**: Ami adds evaluator and auditing layers across skill gaps, learner profiles, generated content, learning plans, and chatbot responses.

## Tech Stack

- **Backend**: Python 3.13, FastAPI, LangChain, Hydra
- **Frontend (current)**: Streamlit
- **Frontend (Beta, in development)**: React SPA
- **Retrieval**: Azure AI Search indexes (`ami-verified-content`, `ami-web-results`) with OpenAI embeddings (`text-embedding-3-small`) + web search wrappers
- **Cloud Services**: Azure AI Search, Azure Blob Storage, Azure Cosmos DB, Azure Document Intelligence
- **Model Routing**: Provider/model overrides via `model_provider` and `model_name`
- **Testing/Evaluation**: Pytest test suites, LLM-as-a-judge eval scripts (RAGAS-based for RAG, rubric-based for agent quality)

## Getting Started

For service-specific setup details:
- Backend guide: [`backend/README.md`](backend/README.md)
- Frontend guide: [`frontend/README.md`](frontend/README.md)

### Quick Start (Local Dev)

#### Step 1 - Prepare backend environment

From repo root:

```bash
cp backend/.env.example backend/.env
```

Fill the required keys in `backend/.env`. For the current backend stack, that typically means:

- `OPENAI_API_KEY`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_COSMOS_CONNECTION_STRING`
- `JWT_SECRET`

Set `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY` as well if you plan to ingest or re-index verified course content from PDFs or slides.

#### Step 2 - Start backend on port 8000 (recommended)

```bash
BACKEND_PORT=8000 ./scripts/start_backend.sh
```

#### Step 3 - Start frontend in another terminal

```bash
./scripts/start_frontend.sh
```

#### Step 4 - Open services

- Frontend: `http://localhost:8501`
- Backend docs: `http://localhost:8000/docs`

### Quick Start (Docker)

Run each service from its directory:

```bash
# backend
cd backend
docker compose -f docker/docker-compose.yml up --build

# frontend (separate terminal)
cd frontend
docker compose -f docker/docker-compose.yml up --build
```

### Optional Helper Scripts

From repo root:

```bash
# Start both services in background (logs/ and pids/ managed by script)
BACKEND_PORT=8000 ./scripts/start_all.sh

# Stop services started by start_all.sh
./scripts/stop_all.sh
```

## Repository Layout

```text
Ami/
  backend/          # FastAPI backend, modules, configs, tests, evals, docker files; runtime data in backend/data/
  frontend/         # Streamlit frontend, pages/components/utils, tests, docker files
  frontend-react/   # React SPA (Beta release, in active development)
  docs/             # design notes, migration docs, testing guides
  scripts/          # local dev startup/stop scripts
  assets/           # architecture diagrams and Beta screenshots
```

## Interface Walkthrough

The screenshots below show the current Beta interface and key adaptive behaviors.

### 1. Login

![Login](assets/Beta/0%20-%20Login.png)

Login interface for returning users to authenticate and access personalized learning sessions.

### 2. Onboarding

![Onboarding](assets/Beta/1%20-%20Onboarding.png)

Onboarding flow where learners select a learning persona (maps to FSLSM dimensions), define a learning goal, and optionally upload a resume.

### 3. Skill Gap Identification

![Skill gap analysis](assets/Beta/2A%20-%20Skill%20Gap.png)

Skill gap analysis grounded in verified course materials and the learner's stated background.

| Verified Content Context | Bias Audit |
|---|---|
| ![Skill gap with verified content](assets/Beta/2C%20-%20Skill%20Gap%20%28Verified%20Content%29.png) | ![Skill gap bias audit](assets/Beta/2B%20-%20Skill%20Gap%20%28Bias%29.png) |

Left: skill gap output grounded in indexed course materials via RAG.
Right: `BiasAuditor` output flagging potentially biased assumptions in the skill gap analysis.

### 4. Learning Path Personalization (FSLSM)

| Active-Sensing-Visual-Sequential Persona | Reflective-Intuitive-Verbal-Global Persona |
|---|---|
| ![Learning path visual persona](assets/Beta/3A%20-%20Learning%20Path%20%28Active-Sensing-Visual-Sequential%29.png) | ![Learning path verbal persona](assets/Beta/3B%20-%20Learning%20Path%20%28Reflective-Intuitive-Verbal-Global%29.png) |

Learning paths personalized by FSLSM profile. Session sequencing and scope are adapted to the learner's cognitive style and SOLO level.

### 5. Learning Session and Content Delivery

![Learning session visual persona](assets/Beta/4A.I%20-%20Learning%20Session%20%28Active-Sensing-Visual-Sequential%29.png)

![Learning session verbal](assets/Beta/4B.I%20-%20Learning%20Session%20%28Reflective-Intuitive-Verbal-Global%29.png)

Content delivery for a verbal/reflective persona, prioritizing narrative explanation and sequential structure.

![Plan quality](assets/Beta/4C%20-%20Plan%20Quality.png)

Plan quality reflexion output: the agentic scheduler evaluates and refines the learning path via embedded plan feedback simulation before presenting it to the learner.

### 6. Adaptive Quizzes and SOLO-based Assessment

| Beginner-Level Quiz | Intermediate-Level Quiz |
|---|---|
| ![Beginner quiz](assets/Beta/5A%20-%20Quiz%20%28Beginner%29.png) | ![Intermediate quiz](assets/Beta/5B%20-%20Quiz%20%28Intermediate%29.png) |

Left: quiz calibrated for foundational (pre-structural/uni-structural) SOLO level.
Right: quiz calibrated for intermediate (multi-structural/relational) SOLO level.

![SOLO-based open-ended assessment](assets/Beta/5C.%20Quiz%20-%20Assessment%20using%20SOLO.png)

Open-ended response assessment graded by an LLM judge aligned with SOLO taxonomy rubrics.

### 7. Ami Chatbot Tutor

![Ami chatbot](assets/Beta/6%20-%20Chatbot.png)

Conversational tutor ("Ami") with request-time tool assembly: session content retrieval, verified-content RAG, web search, media search, and signal-gated FSLSM preference updates.

### 8. Learner Profile

| Learner Information and Cognitive Status | Learning Preferences and Patterns |
|---|---|
| ![Learner profile info and cognitive status](assets/Beta/7%20-%20Learner%20Profile%20%28Learner%20Information%20and%20Cognitive%20Status%29.png) | ![Learner profile preferences and patterns](assets/Beta/7B%20-%20Learner%20Profile%20%28Preferences%20and%20Patterns%29.png) |

Left: current cognitive status (SOLO level) and learner background.
Right: FSLSM learning style dimensions and behavioral signals accumulated from sessions.

### 9. Edit Profile

| FSLSM Edit | Learner Information Edit |
|---|---|
| ![Edit FSLSM profile](assets/Beta/8A%20-%20Edit%20Profile%20%28FSLSM%29.png) | ![Edit learner information](assets/Beta/8B%20-%20Edit%20Profile%20%28Learner%20Information%29.png) |

FSLSM dimension updates and personal/background information updates are separated into distinct edit flows to prevent unintended cross-field changes.

### 10. Goal Management

![Goal management page](assets/Beta/9%20-%20Goal%20Management.png)

Goal Management page for creating, selecting, and switching among multiple learning goals.

### 11. Learning Analytics

![Learning analytics dashboard](assets/Beta/10%20-%20Analytics%20Dashboard.png)

Learning Analytics dashboard showing progress, performance, and engagement metrics over time.

## Project Context

This project is developed as part of **GNG 5902 (Winter 2026)** at the University of Ottawa.

- **Client**: Dr. Ali Abbas — CEO of Smart Digital Medicine, Adjunct Professor at uOttawa
- **Technical Advisor**: Prof. Ismaeel Al-Ridhawi — Associate Professor, School of Electrical Engineering and Computer Science, uOttawa

### Team (Group 5)

| Member | Role |
|---|---|
| Thuy Tran | Project Manager / Project Coordinator |
| Nellie Le | Learning Researcher |
| Mico Comia | Technical Lead (Multi-agent AI & LLM Integration) |
| Tianci Li | Technical & Ethical Framework |
| Tian Lai | UX Design Lead |
| Xinping Wang | UX Engineer |

## References

1. T. Wang et al., "LLM-powered Multi-agent Framework for Goal-oriented Learning in Intelligent Tutoring System," WWW '25, May 2025. [Paper](https://arxiv.org/pdf/2501.15749)
2. M. Rizvi, "Investigating AI-Powered Tutoring Systems that Adapt to Individual Student Needs," EPESS, vol. 31, Oct. 2023.
3. Biggs, J. B., & Collis, K. F. (1982). *Evaluating the Quality of Learning: The SOLO Taxonomy*. Academic Press.
4. Felder, R. M., & Silverman, L. K. (1988). "Learning and teaching styles in engineering education." *Engineering Education*, 78(7), 674-681.

## Original Citation

```bibtex
@inproceedings{wang2025llm,
  title={LLM-powered Multi-agent Framework for Goal-oriented Learning in Intelligent Tutoring System},
  author={Wang, Tianfu and Zhan, Yi and Lian, Jianxun and Hu, Zhengyu and Yuan, Nicholas Jing and Zhang, Qi and Xie, Xing and Xiong, Hui},
  booktitle={Companion Proceedings of the ACM Web Conference},
  year={2025}
}
```
