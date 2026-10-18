"""Terminal AI agent that can use calculator and weather tools via the Claude API.

Every step of the agent loop is printed so you can watch it work.
"""

import ast
import json
import operator

import anthropic
import requests
from dotenv import load_dotenv

from weather import get_weather_for_city

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
MAX_TOOL_ROUNDS = 10  # safety cap so a bug can't loop forever and burn credits

SYSTEM_PROMPT = (
    "You are a helpful terminal assistant. "
    "Always use the calculator tool for arithmetic instead of doing it in your head. "
    "Use get_weather for any question about current weather or the forecast."
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

TOOLS = [CALCULATOR_TOOL, WEATHER_TOOL]

# --- The tool itself: plain Python, no knowledge of Claude --------------------
# Maps each allowed syntax-tree node type to the Python function that runs it.
BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPERATORS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_calculate(expression):
    """Evaluate arithmetic safely. Raises ValueError for anything that isn't math.

    We never use eval(): it would run *any* Python code Claude sends.
    Instead we parse the text into a syntax tree and only allow numbers
    and math operators.
    """
    tree = ast.parse(expression, mode="eval")
    return _evaluate_node(tree.body)


def _evaluate_node(node):
    """Recursively evaluate one node of the syntax tree."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent too large (max 100).")
        return BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def run_calculator(tool_input):
    return str(safe_calculate(tool_input["expression"]))


def run_get_weather(tool_input):
    weather = get_weather_for_city(tool_input["city"], tool_input["unit"])
    return json.dumps(weather)  # tool_result content must be text


# Tool name (as Claude sends it) -> the Python function that runs it.
TOOL_FUNCTIONS = {
    "calculator": run_calculator,
    "get_weather": run_get_weather,
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


def handle_tool_calls(response):
    """Run every tool_use block in the response. Return the tool_result blocks."""
    tool_results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        print(f"  🔧 Claude asks for tool: {block.name}")
        print(f"     tool_use id: {block.id}")
        print(f"     input:       {json.dumps(block.input)}")

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

    print("Agent with calculator + weather tools. Type 'quit' to exit.")
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
