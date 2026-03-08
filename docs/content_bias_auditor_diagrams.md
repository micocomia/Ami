# Content Bias Auditor — Diagrams

## 1. Content Bias Auditor Pipeline Flow

```mermaid
flowchart LR
    A[Content Generated] --> B[Bias Auditor Triggered]
    B --> C[LLM Audit]
    B --> D[Deterministic Scan]
    C --> E[Merge Results]
    D --> E
    E --> F{Deterministic flags found\nbut LLM said low?}
    F -- Yes --> G[Escalate to Medium risk]
    F -- No --> H[Keep LLM risk level]
    G --> I[Return Audit Result]
    H --> I
    I --> J[Frontend Renders Banners]
```

## 2. Dual-Layer Detection Architecture

```mermaid
flowchart TB
    subgraph LLM["LLM-Based Audit"]
        R[Representation Bias]
        L[Language Bias]
        D[Difficulty Bias]
        S[Source Bias]
    end

    subgraph DET["Deterministic Scan"]
        K[Keyword Matching\n15 known biased phrases]
    end

    Content[Generated Content] --> LLM
    Content --> DET

    LLM --> Merge[Merge Flags + Risk Escalation]
    DET --> Merge
    Merge --> Result[ContentBiasAuditResult]
```

## 3. Frontend Rendering Decision Tree

```mermaid
flowchart TD
    A[Knowledge Document Page Loads] --> B{Audit result\navailable?}
    B -- No --> C[Show Fallback\nEthical Disclaimer]
    B -- Yes --> D[Show Ethical Disclaimer]
    D --> E{Overall bias\nrisk level?}
    E -- Low --> F[No additional warnings]
    E -- Medium --> G["Show Moderate Risk Banner\n(flagged/audited section count)"]
    E -- High --> H["Show High Risk Banner\n(flagged/audited section count)"]
    G --> I{Bias flags\nexist?}
    H --> I
    F --> I
    I -- Yes --> J[Show Expandable\nBias Audit Details]
    I -- No --> K[Done]
    J --> K
```

## 4. Full-Stack Integration Diagram

```mermaid
flowchart TB
    subgraph Frontend["Frontend (Streamlit)"]
        KD[Knowledge Document Page]
        API[audit_content_bias\nAPI utility]
        RB[render_content_bias_banners\ncomponent]
    end

    subgraph Backend["Backend (FastAPI)"]
        EP["/audit-content-bias"\nendpoint]
        Agent[ContentBiasAuditor\nagent]
    end

    subgraph Detection["Detection Layers"]
        LLM[LLM Audit\n4 bias categories]
        DET[Deterministic Scan\n15 biased phrases]
    end

    KD -->|1. Content generated| API
    API -->|2. POST request| EP
    EP -->|3. Invoke auditor| Agent
    Agent -->|4a. Prompt LLM| LLM
    Agent -->|4b. Keyword scan| DET
    LLM -->|5a. LLM flags| Agent
    DET -->|5b. Deterministic flags| Agent
    Agent -->|6. Merged audit result| EP
    EP -->|7. JSON response| API
    API -->|8. Pass audit data| RB
    RB -->|9. Render banners| KD
```
