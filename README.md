# My Agent

A terminal AI agent built on the [Claude API](https://docs.claude.com/) with
**tool use**. You chat with Claude, and Claude can call Python functions
(tools) to do math, check the weather, manage a to-do list and summarize your
expenses.

The agent loop is written by hand and prints every step, so you can watch
exactly how an AI agent works: when Claude asks for a tool, what input it
sends, and what result goes back.

## Features

- **6 tools**: calculator, live weather, list/add/complete to-do tasks,
  and expense summaries
- **Visible agent loop**: every `stop_reason`, `tool_use` request and
  `tool_result` is printed
- **Approval for changes**: tools that change data (`add_task`,
  `complete_task`) ask `Allow? (y/n)` first; read-only tools run without asking
- **Safe calculator**: no `eval()`, with limits so huge numbers can't freeze
  the program
- **Errors don't crash it**: tool errors (like an unknown city) are sent back to
  Claude so it can explain them, and API errors print a message instead of a
  traceback
- **Safety cap**: at most 10 tool rounds per message, so it can't loop forever

## Example

```
$ python agent.py
Agent with calculator, weather, to-do and expenses tools. Type 'quit' to exit.
You: What's the weather in Tokyo in Fahrenheit, and how much warmer is today's high than the low?

[step 1] Sending 1 message(s) to Claude...
[step 1] stop_reason = 'tool_use'
  🔧 Claude asks for tool: get_weather
     tool_use id: toolu_01S2R9vFXJBcJoQk1JY2JYmS
     input:       {"city": "Tokyo", "unit": "F"}
     result returned: {"location": "Tokyo, Japan", "temperature": 63.4, "high": 77.8, "low": 62.0, ...}
  ↩️  Sending 1 tool_result(s) back to Claude

[step 2] Sending 3 message(s) to Claude...
[step 2] stop_reason = 'tool_use'
  🔧 Claude asks for tool: calculator
     tool_use id: toolu_01GakxH1jXqbBFRHfBFS8YGa
     input:       {"expression": "77.8 - 62.0"}
     result returned: 15.799999999999997
  ↩️  Sending 1 tool_result(s) back to Claude

[step 3] Sending 5 message(s) to Claude...
[step 3] stop_reason = 'end_turn'

Claude: Tokyo's high today is 15.8°F warmer than the low (77.8°F vs. 62.0°F). ...
```

Claude decided by itself to get the weather first and then do the math.

## Tools

| Tool | What it does | Asks first? |
|---|---|---|
| `calculator` | Evaluates arithmetic like `(3 + 4) * 2` | No |
| `get_weather` | Current weather and a 3-day forecast for a city ([Open-Meteo](https://open-meteo.com/), no key needed) | No |
| `list_tasks` | Shows your to-do list | No |
| `add_task` | Adds a task to the list | **Yes** |
| `complete_task` | Marks a task as done, by id | **Yes** |
| `expenses_summary` | Total spent, or totals per category, for all time or one month | No |

## Requirements

- Python 3.11 or newer (pandas 3 needs 3.11; built with 3.13)
- An [Anthropic API key](https://console.anthropic.com/)
- Python packages listed in `requirements.txt`:
  [`anthropic`](https://pypi.org/project/anthropic/),
  [`python-dotenv`](https://pypi.org/project/python-dotenv/),
  [`requests`](https://pypi.org/project/requests/) and
  [`pandas`](https://pypi.org/project/pandas/)

## Setup

1. Create a virtual environment and install the dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a file called `.env` in the project folder with your API key:

   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

   `.env` is listed in `.gitignore`, so your key is never committed.
   Never share this file or paste the key into code.

3. *(Optional)* Create `expenses.csv` for the expenses tool:

   ```
   date,category,amount,note
   2026-09-27,grocery,330.0,Nesto
   2026-09-27,restaurant,500.0,dinner
   ```

   `date` must be `YYYY-MM-DD`. The `note` column is optional.

## Usage

```bash
source .venv/bin/activate
python agent.py
```

Type a question and press Enter. Type `quit` (or press Ctrl-C) to exit.
Things to try:

- `What is 15% of 240?`
- `Weather in Paris in Fahrenheit?`
- `Add 'buy milk' to my list, then show my tasks`
- `I bought the milk!` (Claude finds the task's id, then asks to complete it)
- `What do I spend the most on?`
- `Weather in Xyzzyville` (watch the error go back to Claude)

## How it works

The API is **stateless**: Claude remembers nothing between calls, so the
program keeps the whole conversation in a `messages` list and sends it every
time. Each user message runs this loop (`run_agent_turn()` in `agent.py`):

```
send messages + tool list to Claude
        │
        ▼
  stop_reason?
   "tool_use"  → run each requested tool (asking first if it changes data)
                 → append Claude's reply and the tool results to messages
                 → loop again (max 10 rounds)
   "end_turn"  → print Claude's answer, wait for your next message
```

1. **Tool definitions** (`CALCULATOR_TOOL`, `WEATHER_TOOL`, …) tell Claude
   each tool's name, a description of when to use it, and a JSON schema for
   its input. Claude never sees the Python code, only these definitions.
2. When Claude wants a tool, it replies with a **`tool_use`** block containing
   an `id`, the tool `name` and its `input`.
3. The program runs the matching Python function and replies with a
   **`tool_result`** that has the same `tool_use_id`. If something went wrong,
   it sets `is_error: true` so Claude can explain the problem or try again.

## Project structure

```
my-agent/
├── agent.py           # Claude API calls, tool definitions, the agent loop
├── calculator.py      # safe arithmetic (AST-based, no eval)
├── weather.py         # Open-Meteo weather lookup
├── tasks.py           # to-do list stored in tasks.json
├── expenses.py        # pandas summaries of expenses.csv
├── requirements.txt   # Python dependencies
├── .env               # your API key (not committed)
├── tasks.json         # your to-do list, created automatically (not committed)
└── expenses.csv       # your expenses (not committed)
```

The tool files (`calculator.py`, `weather.py`, `tasks.py`, `expenses.py`) are
plain Python and know nothing about Claude. `agent.py` connects them to Claude
through the `TOOL_FUNCTIONS` dispatch table.

## Adding a new tool

1. Write the function in its own module.
2. Add a tool definition (name, description, `input_schema`) in `agent.py`
   and add it to `TOOLS`.
3. Add a `run_...` function and register it in `TOOL_FUNCTIONS`.
4. If the tool changes data, add its name to `TOOLS_NEEDING_APPROVAL`.

The agent loop itself doesn't need to change.

## Limitations

- No automated tests yet. Everything has been tested by hand.
- The conversation grows with every message, so long chats cost more per request.
- `expenses.csv` amounts have no currency; Claude won't assume one.

## Credits

Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Built with the [Claude API](https://docs.claude.com/) by Anthropic.
