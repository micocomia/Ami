"""Configuration for the Beta evaluation suite."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BETA_BASE_URL = os.getenv("BETA_BASE_URL", "http://localhost:8000/v1").rstrip("/")
DEFAULT_MODEL_PROVIDER = os.getenv("DEFAULT_MODEL_PROVIDER", None)
DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", None)
JUDGE_PROVIDER = os.getenv("JUDGE_MODEL_PROVIDER", "openai")
JUDGE_MODEL = os.getenv("JUDGE_MODEL_NAME", "gpt-4o-mini")
DEFAULT_SESSION_COUNT = int(os.getenv("EVAL_SESSION_COUNT", "5"))
EVAL_USERNAME = os.getenv("EVAL_USERNAME", "beta_eval_user")
EVAL_PASSWORD = os.getenv("EVAL_PASSWORD", "beta_eval_password")

VERSION_KEY = "current"
VERSION_LABEL = "Ami Backend (Current)"

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
