<div align="center">
  <p><b>Ami: Adaptive Mentoring Intelligence</b></p>
  <p>An enhanced fork of GenMentor — LLM-powered & Goal-oriented Tutoring System</p>
</div>

---

## Overview

This repository is a **fork of [GenMentor](https://arxiv.org/pdf/2501.15749)** (WWW 2025, Industry Track — Oral Presentation), an LLM-powered multi-agent framework for goal-oriented learning in Intelligent Tutoring Systems (ITS). Our group is building upon GenMentor to create a **Cognitive-Style Adaptive AI Tutor** that delivers truly personalized learning experiences. We are calling this enhanced fork Ami: Adaptive Mentoring Intelligence system.

Modern digital education often adopts a "one-size-fits-all" approach, failing to account for the diverse cognitive needs of individual learners. Students, professionals, and lifelong learners frequently struggle with content that is either too complex for their current knowledge level or presented in a format that does not align with their unique cognitive styles. This leads to disengagement, fragmented learning progress, and time wasted on inefficient study methods.

Our project addresses this gap by enhancing GenMentor with:

- **Verified educational content** as the source for content generation (via RAG and web search)
- **Pedagogically-grounded learner profiling** based on the Felder-Silverman learning styles model and the SOLO Taxonomy
- **More granular evaluation of students** through improved assessment mechanisms
- **A React-based frontend** being developed in parallel for a responsive, accessible user experience, while this repository maintains a Streamlit frontend as an alternative

## Key Improvements Over GenMentor

| Area | Original GenMentor | Ami |
|---|---|---|
| Content Sources | LLM-generated only | Verified materials via RAG + web search |
| Learner Profiling | Basic profile | Grounded in Felder-Silverman & SOLO Taxonomy |
| Student Evaluation | Coarse assessment | More granular, rubric-based evaluation |
| Frontend | Streamlit | React SPA (in parallel development) + Streamlit alternative maintained in this repository |
| Learner Simulation | N/A | Learner simulator agent for content quality feedback loop |

## System Architecture

<div align="center">
  <p align="center">
    <img src="resources/g5-framework.png" alt="System Architecture" width="700" style="box-shadow: 0 8px 24px rgba(0,0,0,0.15); border-radius: 8px;"/>
  </p>
</div>

### Agent Modules

1. **Learner Profiler** — Determines the learner's cognitive ability and learning preferences using attributes based on pedagogical studies (Felder-Silverman model), giving the system a holistic view of how each learner most effectively learns.

2. **Skill Gap Identifier** — Analyzes the gap between what the learner wants to learn and their current skills, enabling targeted learning paths and materials.

3. **Learning Plan Generator** — Generates a personalized learning plan that continuously adjusts based on the student's progress and difficulty level.

4. **Content Generator and Evaluator** — Generates personalized content and assessments tailored to learner preferences. Decides whether to source content from verified materials (via RAG) or web search.

5. **Learner Simulator** — Simulates the student to evaluate the quality of learning paths and content, creating a feedback loop for continuous improvement.

## Tech Stack

- **Backend**: Python, FastAPI, LangChain, OpenAI/Google/Meta LLMs
- **Frontend**: React (in parallel development), Streamlit (maintained alternative in this repository)
- **Content Retrieval**: RAG (Retrieval Augmented Generation) via LangChain vector stores
- **Evaluation**: RAGAS for the assessment of the RAG system and LLM-as-a-judge for the evaluation of the agents
- **Design**: Figma for prototyping and design system

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

## Getting Started

For setup and usage instructions, see the respective directories:

- [`backend/`](backend/) — Backend installation, configuration, and running instructions
- [`frontend/`](frontend/) — Frontend installation, configuration, and running instructions

## MVP Interface Walkthrough

The screenshots below show the current MVP interfaces and key adaptive behaviors.

### 1. Login

![Login page](resources/MVP/1.%20Login.png)

Login interface for returning users to authenticate and access personalized learning sessions.

### 2. Onboarding

![Onboarding page](resources/MVP/2.%20Onboarding.png)

Onboarding flow where learners select a persona, define a learning goal, and optionally upload a resume.

### 3. Skill Gap Identification

| Verified Content Context | Resume-Aware Skill Gap |
|---|---|
| ![Skill gap with verified content](resources/MVP/3a.%20Skill%20Gap%20-%20Verified%20Content.png) | ![Skill gap adjusted with resume](resources/MVP/3b.%20Skill%20Gap%20-%20with%20Resume.png) |

Left: skill gap analysis grounded in verified course materials, demonstrating accurate context retrieval.  
Right: skill gap output after resume ingestion, showing automatic recalibration of inferred proficiency.

![Skill gap bias audit](resources/MVP/3c.%20Skill%20Gap%20-%20Bias.png)

Bias-auditor view flagging potentially biased assumptions in skill gap analysis.

### 4. Learning Path Personalization (FSLSM)

| Visual-Leaning Persona | Verbal-Leaning Persona |
|---|---|
| ![Learning path visual persona](resources/MVP/4a.%20Learning%20Path%20Page%20-%20Visual.png) | ![Learning path verbal persona](resources/MVP/4b.%20Learning%20Path%20-%20Verbal.png) |

Left: learning path page for a visual-leaning persona, emphasizing visual structure and cues.  
Right: learning path page for a verbal-leaning persona, emphasizing text-forward guidance.

### 5. Content Delivery Personalization

| Visual Persona Content | Verbal Persona Content |
|---|---|
| ![Visual content delivery](resources/MVP/5a.%20Content%20-%20Visual.png) | ![Verbal content delivery](resources/MVP/5b.%20Content%20-%20Verbal.png) |

Left: content delivery for a visual persona, with stronger visual organization and representation.  
Right: content delivery for a verbal persona, prioritizing narrative and text-based explanation.

### 6. Adaptive Quizzes and SOLO-based Assessment

| Beginner-Level Quiz | Intermediate-Level Quiz |
|---|---|
| ![Beginner quiz](resources/MVP/6a.%20Quiz%20beginner.png) | ![Intermediate quiz](resources/MVP/6b.%20Quiz%20-%20intermediate.png) |

Left: quiz set for beginner-level proficiency, focused on foundational difficulty.  
Right: quiz set for intermediate-level proficiency, with higher conceptual depth.

![SOLO-based open-ended assessment](resources/MVP/6c.%20Quiz%20-%20Assessment%20using%20SOLO.png)

Open-ended response assessment using an LLM grader aligned with SOLO taxonomy rubrics.

### 7. Learner Profile Views

| Cognitive Status | Learning Preference and Behavior |
|---|---|
| ![Learner profile cognitive status](resources/MVP/7a.%20Learner%20Profile%20-%20Cognitive%20Status.png) | ![Learner profile preferences and behavior](resources/MVP/7b.%20Learner%20Profile%20-%20Learning%20PReference%20and%20Behavior.png) |

Left: learner profile view summarizing current cognitive status indicators.  
Right: learner profile view summarizing learning preferences and behavioral signals.

![Learner profile with resume](resources/MVP/7c.%20Learner%20Profile%20-%20Resume.png)

Profile enrichment after resume upload, showing additional inferred background attributes.

### 8. Goal Management

![Goal management page](resources/MVP/8a.%20Goal%20Management%20Page.png)

Goal Management page for creating, selecting, and switching among multiple learning goals.

### 9. Learning Analytics

![Learning analytics page](resources/MVP/9.%20Learning%20Analytics.png)

Learning Analytics dashboard showing progress, performance, and engagement metrics over time.

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
