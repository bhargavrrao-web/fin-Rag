"""Agent tests with a scripted fake LLM: no network, no API key."""
import json
from types import SimpleNamespace

from app.agent import parse_final, run_agent
from app.config import Settings
from app.tools import ToolBox

SETTINGS = Settings(_env_file=None, llm_model="fake-model")
FINAL = json.dumps({"answer": "Revenue was 100.", "status": "answered",
                    "citations": [{"company": "acme", "fiscal_year": 2024, "page": 7}]})


def tool_msg(name, args, call_id="c1"):
    call = SimpleNamespace(id=call_id, function=SimpleNamespace(name=name,
                                                                arguments=json.dumps(args)))
    return SimpleNamespace(content=None, tool_calls=[call])


def text_msg(text):
    return SimpleNamespace(content=text, tool_calls=None)


class ScriptedLLM:
    """Returns the queued messages one by one and records every call."""

    def __init__(self, *messages):
        self.queue, self.calls = list(messages), []

    def __call__(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.queue.pop(0))], usage=usage)


BOX = ToolBox(retriever=None)  # calculator needs no retriever


def test_tool_call_then_final_answer():
    llm = ScriptedLLM(tool_msg("calculator", {"expression": "100*1.1"}), text_msg(FINAL))
    r = run_agent("q", BOX, SETTINGS, completion=llm)
    assert r.status == "answered" and r.answer == "Revenue was 100."
    assert r.citations[0].page == 7
    assert [s["tool"] for s in r.steps] == ["calculator"]
    assert r.steps[0]["result_preview"].startswith("110")
    assert (r.prompt_tokens, r.completion_tokens) == (20, 10)
    # the tool result was fed back to the model, and temperature is 0
    assert llm.calls[1]["messages"][-1]["role"] == "tool"
    assert all(c["temperature"] == 0 for c in llm.calls)


def test_tool_error_is_returned_to_model_not_raised():
    llm = ScriptedLLM(tool_msg("calculator", {"expression": "1/0"}), text_msg(FINAL))
    r = run_agent("q", BOX, SETTINGS, completion=llm)
    assert r.steps[0]["result_preview"] == "ERROR: division by zero"
    assert llm.calls[1]["messages"][-1]["content"] == "ERROR: division by zero"
    assert r.status == "answered"


def test_malformed_json_retries_once():
    llm = ScriptedLLM(text_msg("sure! the answer is 100"), text_msg(FINAL))
    r = run_agent("q", BOX, SETTINGS, completion=llm)
    assert r.status == "answered" and len(llm.calls) == 2
    assert "not valid" in llm.calls[1]["messages"][-1]["content"]


def test_malformed_twice_gives_up_gracefully():
    llm = ScriptedLLM(text_msg("nope"), text_msg("still nope"))
    r = run_agent("q", BOX, SETTINGS, completion=llm)
    assert r.status == "not_found" and "valid answer" in r.answer


def test_not_found_answer():
    final = json.dumps({"answer": "Not in documents.", "citations": [], "status": "not_found"})
    r = run_agent("q", BOX, SETTINGS, completion=ScriptedLLM(text_msg(final)))
    assert r.status == "not_found" and r.citations == []


def test_max_steps_forces_final_answer_without_tools():
    calc = tool_msg("calculator", {"expression": "1+1"})
    llm = ScriptedLLM(calc, calc, text_msg(FINAL))
    r = run_agent("q", BOX, SETTINGS, completion=llm, max_steps=3)
    assert [c["tool_choice"] for c in llm.calls] == ["auto", "auto", "none"]
    assert r.status == "answered"


def test_ran_out_of_steps():
    calc = tool_msg("calculator", {"expression": "1+1"})
    r = run_agent("q", BOX, SETTINGS, completion=ScriptedLLM(calc, calc), max_steps=2)
    # the fake model ignores tool_choice="none" and calls a tool again on the last step
    assert "ran out of steps" in r.answer and len(r.steps) == 2


def test_parse_final_accepts_code_fences():
    assert parse_final(f"```json\n{FINAL}\n```").status == "answered"
