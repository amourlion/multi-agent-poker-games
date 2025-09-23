# Repository Guidelines

## Project Structure & Module Organization
The simulation core lives in `engine.py`, coordinating deck management, discard rules, and payouts. Agents are defined in `agent_random.py` and `agent_llm.py`; use these as templates when adding new strategies. Card models sit in `deck.py` and scoring logic in `hand_eval.py`, while shared enums and dataclasses live in `game_types.py`. `runner.py` exposes the CLI entry point, and structured match output defaults to `out.jsonl`. Keep tests under `tests/`, mirroring the module layout (e.g., `tests/test_hand_eval.py`).

## Build, Test & Development Commands
Create a virtual environment and install dependencies with `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`; if the requirements file is missing, install `openai`, `pydantic`, and `typer` directly. Use `python runner.py --games 20 --seed 42 --model gpt-4.1-mini --log out.jsonl` for end-to-end simulations. Run the automated suite via `pytest`, and target individual cases with `pytest tests/test_hand_eval.py -k straight`.

## Coding Style & Naming Conventions
All Python modules follow PEP 8: four-space indentation, snake_case for functions, and CapWords for dataclasses and enums. Maintain module-level docstrings similar to the existing files, and favor explicit type hints, especially for public methods and data structures. Keep new modules in lowercase filenames and colocate helper utilities near their consumers.

## Testing Guidelines
Add regression coverage in `tests/` with file names prefixed by `test_`. Each new hand-ranking rule or agent behavior must include deterministic fixtures that assert rankings and discard choices. Run `pytest` before opening a pull request and include the command output in your PR. When modifying randomness, offer a reproducible seed in tests.

## Commit & Pull Request Guidelines
Commit messages in this repository are short imperatives (e.g., `Fix: found that openai API need billing info to work`) and occasionally use prefixes like `docs:`. Follow the same tone, keeping subject lines under 72 characters. Pull requests should link to any relevant issues, summarize behavioral changes, and paste the `pytest` or `runner.py` invocation you used for validation. Add screenshots or log excerpts when the change affects telemetry or CLI output.

## Agent & Secrets Notes
Never hard-code API keys; rely on the `OPENAI_API_KEY` environment variable described in `README.md`. When creating new agents, surface fallbacks similar to `_conservative_fallback` and log decisions through `logger.py` to keep analytics consistent.
