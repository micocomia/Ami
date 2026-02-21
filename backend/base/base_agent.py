import json
from typing import Any, Dict, Optional, Sequence

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from utils.llm_output import convert_json_output, preprocess_response
from langgraph.typing import InputT, OutputT, StateT
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    JumpTo,
    ModelRequest,
    ModelResponse,
    OmitFromSchema,
    _InputAgentState,
    _OutputAgentState,
)

valid_agent_arg_list = [
    "middleware",
    "response_format",
    "state_schema",
    "context_schema",
    "checkpointer",
    "store",
    "interrupt_before",
    "interrupt_after",
    "debug",
    "name",
    "cache"
]


class BaseAgent:

    def __init__(
            self,
            model: BaseChatModel,
            system_prompt: Optional[str] = None,
            tools: Optional[list[Any]] = None,
            **kwargs
        ) -> None:
        """Initialize a base agent with JSON output and validation."""
        self._model = model
        self._system_prompt = system_prompt
        self._tools = tools
        self._agent_kwargs = {k: v for k, v in kwargs.items() if k in valid_agent_arg_list}
        self._agent = self._build_agent()
        self.exclude_think = kwargs.get("exclude_think", True)
        self.jsonalize_output = kwargs.get("jsonalize_output", True)

    def _build_agent(self):
        return create_agent(
            model=self._model,
            tools=self._tools,
            system_prompt=self._system_prompt,
            **self._agent_kwargs,
        )

    def set_prompts(self, system_prompt: Optional[str] = None, task_prompt: Optional[str] = None) -> None:
        """Set or update system/task prompts and rebuild the internal agent if needed."""
        if system_prompt is not None:
            self._system_prompt = system_prompt
        if task_prompt is not None:
            self._task_prompt = task_prompt
        self._agent = self._build_agent()

    def _build_prompt(self, variables: Dict[str, Any], task_prompt: Optional[str] = None) -> _InputAgentState:
        """Build chat messages for model call."""
        assert task_prompt is not None, "Either self._task_prompt or task_prompt must be provided."
        task_prompt = task_prompt
        formatted_task = task_prompt.format(**variables)  # type: ignore[union-attr]
        prompt = {
            "messages": [
                {"role": "user", "content": formatted_task}
            ]
        }
        return prompt

    def invoke(self, input_dict: dict, task_prompt: Optional[str] = None, max_retries: int = 2, **kwargs) -> Any:
        """Invoke the agent with the given input text.

        When JSON output is expected and the LLM response fails to parse,
        the conversation is extended with the failed response and a
        correction prompt, then re-invoked up to *max_retries* times.

        Kwargs:
            recursion_limit: Max LangGraph graph steps (default 25).
        """
        input_prompt = self._build_prompt(input_dict, task_prompt=task_prompt)

        invoke_config = {"recursion_limit": kwargs.get("recursion_limit", 25)}

        for attempt in range(1 + max_retries):
            raw_output = self._agent.invoke(input_prompt, config=invoke_config)

            # Extract text and strip <think> tags without JSON parsing.
            text_output = preprocess_response(
                raw_output, only_text=True, exclude_think=self.exclude_think, json_output=False
            )

            if not self.jsonalize_output:
                return text_output

            try:
                return convert_json_output(text_output)
            except json.JSONDecodeError:
                if attempt < max_retries:
                    input_prompt = {
                        "messages": input_prompt["messages"] + [
                            {"role": "assistant", "content": text_output},
                            {"role": "user", "content": (
                                "Your previous response could not be parsed as valid JSON. "
                                "Please return ONLY a valid JSON object with no additional "
                                "text, markdown formatting, or code fences."
                            )},
                        ]
                    }
                else:
                    raise
