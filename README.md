<div align="center">
  <p><b>Cognitive-Style Adaptive AI Tutor</b></p>
  <p>An enhanced fork of GenMentor — LLM-powered & Goal-oriented Tutoring System</p>
</div>

---

## Overview

This repository is a **fork of [GenMentor](https://arxiv.org/pdf/2501.15749)** (WWW 2025, Industry Track — Oral Presentation), an LLM-powered multi-agent framework for goal-oriented learning in Intelligent Tutoring Systems (ITS). Our group is building upon GenMentor to create a **Cognitive-Style Adaptive AI Tutor** that delivers truly personalized learning experiences.

Modern digital education often adopts a "one-size-fits-all" approach, failing to account for the diverse cognitive needs of individual learners. Students, professionals, and lifelong learners frequently struggle with content that is either too complex for their current knowledge level or presented in a format that does not align with their unique cognitive styles. This leads to disengagement, fragmented learning progress, and time wasted on inefficient study methods.

Our project addresses this gap by enhancing GenMentor with:

- **Verified educational content** as the source for content generation (via RAG and web search)
- **Pedagogically-grounded learner profiling** based on the Felder-Silverman learning styles model and the SOLO Taxonomy
- **More granular evaluation of students** through improved assessment mechanisms
- **A React-based frontend** for a responsive, accessible user experience (replacing the original Streamlit-only interface)

## Key Improvements Over GenMentor

| Area | Original GenMentor | Our Enhancement |
|---|---|---|
| Content Sources | LLM-generated only | Verified materials via RAG + web search |
| Learner Profiling | Basic profile | Grounded in Felder-Silverman & SOLO Taxonomy |
| Student Evaluation | Coarse assessment | More granular, rubric-based evaluation |
| Frontend | Streamlit | React SPA + Streamlit fallback |
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
- **Frontend**: React (primary), Streamlit (fallback demo)
- **Content Retrieval**: RAG (Retrieval Augmented Generation) via LangChain vector stores
- **Evaluation**: BERTScore (recall & precision) for content adaptation quality
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
