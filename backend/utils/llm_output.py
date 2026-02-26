import re
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _fix_invalid_escapes(s: str) -> str:
    """Replace invalid JSON backslash escapes with double-backslashes.

    JSON only allows: \\", \\\\, \\/, \\b, \\f, \\n, \\r, \\t, \\uXXXX.
    Any other \\X sequence (e.g. \\S from LaTeX) is invalid and will cause
    json.loads to fail.  This helper doubles those backslashes so the
    literal text is preserved.
    """
    return re.sub(
        r'\\(?!["\\/bfnrtu])',
        r'\\\\',
        s,
    )


def convert_json_output(output: str) -> Dict[str, Any]:
    """
    Convert raw JSON output from the LLM into structured format.

    Args:
        output: The JSON output from the LLM

    Returns:
        Structured JSON output
    """
    output = output.strip()
    if output.startswith("```json"):
        output = output[7:].strip()
    if output.endswith("```"):
        output = output[:-3].strip()
    if output.endswith("```json"):
        output = output[:-7].strip()
    try:
        # Attempt to parse the output as JSON
        return json.loads(output)
    except json.JSONDecodeError:
        pass
    # Fix invalid escape sequences and retry
    fixed = _fix_invalid_escapes(output)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Try to extract JSON object from the output string
    start_idx = output.find('{')
    end_idx = output.rfind('}') + 1
    if start_idx != -1 and end_idx != 0:
        json_str = output[start_idx:end_idx]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_fix_invalid_escapes(json_str))
        except json.JSONDecodeError:
            pass
    # Last resort: use json-repair to fix structural issues such as
    # unescaped double quotes inside string values (common in LLM markdown output)
    try:
        from json_repair import repair_json
        repaired = repair_json(output, return_objects=True)
        if isinstance(repaired, dict) and repaired:
            return repaired
    except Exception:
        pass
    logger.error(
        "All JSON parse attempts failed. Raw LLM output (first 500 chars):\n%s",
        output[:500],
    )
    raise json.JSONDecodeError("No valid JSON found in response", output, 0)

def get_text_from_response(response):
    """Extract text from the response object."""
    if 'messages' in response:
        return response['messages'][-1].content
    if 'message' in response['choices'][0]:
        return response['choices'][0]['message']['content']
    return response['choices'][0]['text']

def extract_think_and_result(info):
    "Extract think and result content from the response info."""
    think_match = re.search(r"<think>(.*?)</think>", info, re.DOTALL)
    think_content = think_match.group(1).strip() if think_match else ''
    result_content = re.sub(r"<think>.*?</think>", "", info, flags=re.DOTALL).strip()
    return think_content, result_content


def preprocess_response(response, only_text=True, exclude_think=False, json_output=False):
    if only_text or exclude_think or json_output:
        response = get_text_from_response(response)
    if exclude_think:
        think_content, result_content = extract_think_and_result(response)
        response = result_content
    if json_output:
        try:
            response = convert_json_output(response)
        except json.JSONDecodeError as e:
            logger.error("JSON parse failed: %s\nRaw output (first 500 chars):\n%s", e, response[:500])
            raise e
    return response

