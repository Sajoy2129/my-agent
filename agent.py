"""Terminal AI agent with calculator, weather and to-do tools via the Claude API.

Every step of the agent loop is printed so you can watch it work.
"""

import json

import anthropic
import requests
from dotenv import load_dotenv

from calculator import safe_calculate
from tasks import add_task, complete_task, list_tasks
from weather import get_weather_for_city

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
MAX_TOOL_ROUNDS = 10  # safety cap so a bug can't loop forever and burn credits

SYSTEM_PROMPT = (
    "You are a helpful terminal assistant. "
    "Always use the calculator tool for arithmetic instead of doing it in your head. "
    "Use get_weather for any question about current weather or the forecast. "
    "Use list_tasks, add_task and complete_task to manage the user's to-do list."
)

# --- The tool definition: what we tell Claude about the tool -----------------
# Claude never sees our Python code, only this description. The name, the
# description and the input_schema (a JSON Schema) are how it decides
# when to call the tool and what input to send.
CALCULATOR_TOOL = {
    "name": "calculator",
    "description": (
        "Evaluate an arithmetic expression and return the numeric result. "
        "Supports + - * / // % ** and parentheses, e.g. '(3 + 4) * 2'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The arithmetic expression to evaluate.",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    },
    "strict": True,  # guarantees Claude's input matches the schema exactly
}

WEATHER_TOOL = {
    "name": "get_weather",
    "description": (
        "Get the current temperature and wind speed, today's high/low, "
        "and a 3-day forecast for a city."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name, e.g. 'Paris' or 'Tokyo'.",
            },
            "unit": {
                "type": "string",
                "enum": ["C", "F"],
                "description": "Temperature unit. Use 'C' unless the user asks for Fahrenheit.",
            },
        },
        "required": ["city", "unit"],
        "additionalProperties": False,
    },
    "strict": True,
}

LIST_TASKS_TOOL = {
    "name": "list_tasks",
    "description": (
        "List every task on the user's to-do list, with its id, title "
        "and whether it is done."
    ),
    # No inputs: an object with no properties.
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "strict": True,
}

ADD_TASK_TOOL = {
    "name": "add_task",
    "description": "Add a new task to the user's to-do list. Returns the new task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short description of the task, e.g. 'Buy milk'.",
            }
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    "strict": True,
}

COMPLETE_TASK_TOOL = {
    "name": "complete_task",
    "description": (
        "Mark a task on the user's to-do list as done, by its id. "
        "If you only know the task's title, call list_tasks first to find its id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "integer",
                "description": "The id of the task to mark as done.",
            }
        },
        "required": ["task_id"],
        "additionalProperties": False,
    },
    "strict": True,
}

TOOLS = [
    CALCULATOR_TOOL,
    WEATHER_TOOL,
    LIST_TASKS_TOOL,
    ADD_TASK_TOOL,
    COMPLETE_TASK_TOOL,
]

# --- Running tools: connect each tool name to its Python function -----------
# The tools themselves live in calculator.py, weather.py and tasks.py and
# know nothing about Claude.
def run_calculator(tool_input):
    return str(safe_calculate(tool_input["expression"]))


def run_get_weather(tool_input):
    weather = get_weather_for_city(tool_input["city"], tool_input["unit"])
    return json.dumps(weather)  # tool_result content must be text


def run_list_tasks(tool_input):
    return json.dumps(list_tasks())


def run_add_task(tool_input):
    return json.dumps(add_task(tool_input["title"]))


def run_complete_task(tool_input):
    return json.dumps(complete_task(tool_input["task_id"]))


# Tools that change data. These need the user's OK before they run;
# read-only tools (calculator, get_weather, list_tasks) run straight away.
TOOLS_NEEDING_APPROVAL = {"add_task", "complete_task"}

# Tool name (as Claude sends it) -> the Python function that runs it.
TOOL_FUNCTIONS = {
    "calculator": run_calculator,
    "get_weather": run_get_weather,
    "list_tasks": run_list_tasks,
    "add_task": run_add_task,
    "complete_task": run_complete_task,
}


def run_tool(name, tool_input):
    """Run the tool Claude asked for. Return (result_text, is_error)."""
    tool_function = TOOL_FUNCTIONS.get(name)
    if tool_function is None:
        return f"Unknown tool: {name}", True
    try:
        return tool_function(tool_input), False
    except (ValueError, SyntaxError, ZeroDivisionError, KeyError) as error:
        # Send the error back to Claude instead of crashing; it can recover.
        return f"Error: {error}", True
    except requests.RequestException as error:
        return f"Error: could not reach the weather service ({error})", True
    except Exception as error:
        # Last resort for anything we didn't expect (e.g. OverflowError):
        # one broken tool call shouldn't crash the whole agent.
        return f"Error: unexpected {type(error).__name__}: {error}", True


# --- The agent loop -----------------------------------------------------------
def ask_claude(client, messages):
    """Send the whole conversation plus the tool list to Claude."""
    return client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
        output_config={"effort": "medium"},
        # If a safety check refuses on Opus, the API retries on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )


def ask_permission():
    """Ask the user to allow a data-changing tool. Only 'y' or 'yes' allows it."""
    try:
        answer = input("     Allow? (y/n): ")
    except (KeyboardInterrupt, EOFError):
        print()
        return False  # when in doubt, don't change data
    return answer.strip().lower() in ("y", "yes")


def handle_tool_calls(response):
    """Run every tool_use block in the response. Return the tool_result blocks."""
    tool_results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        print(f"  🔧 Claude asks for tool: {block.name}")
        print(f"     tool_use id: {block.id}")
        print(f"     input:       {json.dumps(block.input)}")

        if block.name in TOOLS_NEEDING_APPROVAL and not ask_permission():
            # We still must answer this tool_use, so tell Claude what happened.
            result_text = "The user declined this action. It was not performed."
            is_error = True
            print("     🚫 declined")
        else:
            result_text, is_error = run_tool(block.name, block.input)
        label = "ERROR returned" if is_error else "result returned"
        print(f"     {label}: {result_text}")

        tool_results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,  # must match the tool_use block's id
                "content": result_text,
                "is_error": is_error,
            }
        )
    return tool_results


def run_agent_turn(client, messages):
    """Loop until Claude gives a final answer for the latest user message."""
    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        print(f"\n[step {round_number}] Sending {len(messages)} message(s) to Claude...")
        response = ask_claude(client, messages)
        print(f"[step {round_number}] stop_reason = {response.stop_reason!r}")

        # Save Claude's reply exactly as it came back (text, tool_use and
        # thinking blocks). The API is stateless: this list is its memory.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_results = handle_tool_calls(response)
            # All results go back together in ONE user message.
            messages.append({"role": "user", "content": tool_results})
            print(f"  ↩️  Sending {len(tool_results)} tool_result(s) back to Claude")
            continue

        if response.stop_reason == "end_turn":
            text = "".join(b.text for b in response.content if b.type == "text")
            print(f"\nClaude: {text}\n")
        elif response.stop_reason == "max_tokens":
            print("\n⚠️  Claude's reply hit the length limit and was cut off.\n")
        elif response.stop_reason == "refusal":
            print("\n⚠️  Claude declined this request.\n")
        else:
            print(f"\n⚠️  Unexpected stop_reason: {response.stop_reason}\n")
        return

    print(f"\n⚠️  Stopped after {MAX_TOOL_ROUNDS} tool rounds (safety cap).\n")


def main():
    load_dotenv()  # reads ANTHROPIC_API_KEY from .env
    client = anthropic.Anthropic()
    messages = []

    print("Agent with calculator, weather and to-do tools. Type 'quit' to exit.")
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break
        if not user_input:
            continue

        turn_start = len(messages)
        messages.append({"role": "user", "content": user_input})
        try:
            run_agent_turn(client, messages)
        except anthropic.AuthenticationError:
            print("❌ Invalid API key. Check ANTHROPIC_API_KEY in your .env file.")
            break
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as error:
            print(f"⚠️  API problem ({type(error).__name__}). Please try again.")
            # Roll back this whole turn so no tool_use is left without a result.
            del messages[turn_start:]


if __name__ == "__main__":
    main()
