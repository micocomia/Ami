"""
Configuration for the comparative evaluation suite.
Set environment variables before running:
  GENMENTOR_BASE_URL   (default: http://localhost:8000)
  ENHANCED_BASE_URL    (default: http://localhost:8001)
  JUDGE_MODEL_PROVIDER (default: openai)
  JUDGE_MODEL_NAME     (default: gpt-4o-mini)
  OPENAI_API_KEY       (required for judge calls)
  ANTHROPIC_API_KEY    (alternative judge provider)
  LANGCHAIN_TRACING_V2 (optional, set to "true" to enable LangSmith tracing)
  LANGCHAIN_API_KEY    (required if tracing enabled)
"""

import os

GENMENTOR_BASE_URL = os.getenv("GENMENTOR_BASE_URL", "http://localhost:8000")
ENHANCED_BASE_URL = os.getenv("ENHANCED_BASE_URL", "http://localhost:8001")

# Default model used by both systems for generation (can be overridden per request)
DEFAULT_MODEL_PROVIDER = os.getenv("DEFAULT_MODEL_PROVIDER", None)
DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", None)

# Judge LLM — used for LLM-as-a-Judge evaluations
JUDGE_PROVIDER = os.getenv("JUDGE_MODEL_PROVIDER", "openai")
JUDGE_MODEL = os.getenv("JUDGE_MODEL_NAME", "gpt-4o-mini")

# Number of sessions to request when scheduling a learning path
DEFAULT_SESSION_COUNT = int(os.getenv("EVAL_SESSION_COUNT", "5"))

# Dataset path
DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

VERSIONS = {
    "genmentor": {
        "label": "GenMentor (Baseline)",
        "base_url": GENMENTOR_BASE_URL,
        "has_fslsm": False,
        "has_solo": False,
        "has_expert_level": False,
    },
    "enhanced": {
        "label": "5902Group5 (Enhanced)",
        "base_url": ENHANCED_BASE_URL,
        "has_fslsm": True,
        "has_solo": True,
        "has_expert_level": True,
    },
}
