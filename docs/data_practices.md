# GenMentor — Data Practices & Privacy Transparency

> **Purpose:** This document describes what data GenMentor collects, how it is stored, what is sent to external services, and how users can control their data. It is intended for team members, reviewers, and as a reference for the in-app transparency notice.

---

## 1. Data We Collect

| Data Type | Collection Point | Required? | Description |
|-----------|-----------------|-----------|-------------|
| Username & password | Registration | Yes | Account credentials. Password is bcrypt-hashed before storage |
| Learning persona | Onboarding | Yes | One of 5 predefined personas (sets FSLSM learning style dimensions) |
| Learning goal | Onboarding | Yes | Free-text description of what the user wants to learn |
| Resume text | Onboarding (PDF upload) | No | Extracted text from an uploaded PDF resume |
| Skill gap assessments | Skill Gap page | Auto | AI-generated skill levels, confidence, and reasoning |
| Learner profile | Profile creation | Auto | AI-generated cognitive status, learning preferences, behavioral patterns |
| Quiz answers & scores | Learning sessions | Auto | Responses to quiz questions and computed mastery scores |
| Session timing | Learning sessions | Auto | Start time, end time, and motivational trigger timestamps per session |
| Behavioral events | Throughout usage | Auto | Typed events (e.g., session completion) with payloads, capped at 200 per user |
| Chat messages | AI Tutor | Auto | Conversation history with the AI tutor |

---

## 2. How Data Is Stored

All data is stored locally on the backend server in JSON files under `backend/data/`:

| Store | File | Contents |
|-------|------|----------|
| Credentials | `users/users.json` | Usernames and bcrypt-hashed passwords |
| Learner profiles | `users/profiles.json` | Per-goal learner profiles (cognitive status, FSLSM, behavioral patterns) |
| User state | `users/user_states.json` | Goals, learning paths, document caches, session timing, UI state |
| Events | `users/events.json` | Behavioral event logs (max 200 per user) |
| Vector store | `vectorstore/` | ChromaDB embeddings of verified course materials (not user data) |

**Storage characteristics:**
- File-based JSON storage (no external database)
- No encryption at rest
- Passwords are bcrypt-hashed with unique salts
- All storage is local to the server

---

## 3. Data Sent to External Services

### LLM API (OpenAI by default)

The following user data is included in prompts sent to the configured LLM provider:

| Feature | Data Sent |
|---------|-----------|
| Skill gap identification | Learning goal + learner information (persona + resume text) |
| Learner profile creation | Learning goal + learner information + skill gaps |
| Bias audit | Learner information + skill gap results |
| Fairness validation | Learner information + learner profile + persona name |
| Learning path generation | Full learner profile |
| Content generation | Learner profile + learning path + session details |
| Profile updates | Current profile + recent interactions + quiz scores |
| AI Tutor chat | Chat history + learner profile |

**Supported LLM providers:** OpenAI (default), Together, DeepSeek, Azure OpenAI, Groq. The active provider depends on environment configuration.

### Web Search (for content retrieval)

When generating learning content, the system may search the web for supplementary materials:
- **DuckDuckGo** (default, privacy-focused)
- **Bing**, **Brave**, or **Serper** (optional, based on configuration)

Search queries are derived from learning topics, not from personal information.

### Embedding Models

- **Sentence Transformers** (all-mpnet-base-v2): Downloaded from Hugging Face on first use, then cached locally. All embedding computation runs locally.

---

## 4. Data Retention

| Data Type | Retention Period |
|-----------|-----------------|
| Account credentials | Until account deletion |
| Learner profiles | Until account deletion |
| User state (goals, paths, caches) | Until account deletion |
| Behavioral events | Rolling window of 200 events per user (older events automatically discarded) |
| Session timing | Until account deletion |
| Course material embeddings | Permanent (not user-specific) |

---

## 5. Account Deletion

Users can permanently delete their account via the **"Delete Account"** button on the My Profile page. Deletion removes:

- Username and password hash from the credentials store
- All learner profiles (across all goals)
- All behavioral events
- All user state (goals, learning paths, session data, document caches, chat history)

After deletion, the username becomes available for re-registration with no residual data.

---

## 6. AI Transparency

GenMentor uses AI extensively. Users are informed through:

| Disclosure | Location | Description |
|------------|----------|-------------|
| Skill gap disclaimer | Skill Gap page | Informs users that skill assessments are AI-generated inferences |
| Profile disclaimer | My Profile page | Informs users that the learner profile is AI-generated from limited information |
| Bias audit banners | Skill Gap page | Shows any detected bias in skill assessments with explanations |
| Fairness validation banners | My Profile page | Shows any fairness concerns in profile generation |
| Data transparency notice | Onboarding page | Summarises data collection, AI usage, and user rights |

---

## 7. Authentication & Session Security

- **Passwords:** Bcrypt-hashed with unique salts (never stored in plaintext)
- **Sessions:** JWT tokens with 24-hour expiry, transmitted via Authorization header
- **No cookies:** Authentication is token-based, not cookie-based
- **CORS:** Currently configured to allow all origins (development setting)

---

## 8. What GenMentor Does NOT Do

- Does not sell or share user data with third parties
- Does not use user data for advertising
- Does not retain data after account deletion
- Does not track users across other websites
- Does not require real names or personally identifiable information (username can be anything)
