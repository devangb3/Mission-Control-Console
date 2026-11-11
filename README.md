# Mission Control

Meridian Launch Services is 90 minutes from a launch. An engineer files an anomaly with a name, a station, three readings, and a note. The console sorts the note, checks the launch limits in code, drafts a briefing, and waits. Only a person can approve it.

The model is a deployment in Microsoft Foundry, called through one client. Tests use a fake of that client, so they need no network and no API key.

## Commands

Requires Python 3.11 or newer and `make`. The commands create `.venv` and
install dependencies on first use. If `python3` is an older system Python,
select a supported interpreter with `make test PYTHON=/path/to/python3.13`
(the same option works with `make start`). To replace an existing environment
that uses an older Python without deleting it, also choose a new path with
`VENV=.venv/new-python`.

Dependency installation is marked complete only after it succeeds. If it fails,
resolve the error and rerun the same command; installation will retry. Changes
to `pyproject.toml` also trigger installation again. Once setup is complete,
tests require neither network access nor an API key.

Start the app:

```
make start
```

Run the tests:

```
make test
```

GitHub Actions runs that command on Python 3.11, 3.12, and 3.13 for each pull request and each push to `main`. The workflow does not use a Foundry key.

`make start` loads `.env` from the repo root. Copy `.env.example` to `.env` and set the Foundry resource URL, API key, and deployment name. The client calls `{resource}/openai/v1/responses` and sends the key as a bearer token. That is the current Foundry route. The Azure AI Inference SDK retired on 26 August 2026.

Set `FOUNDRY_INPUT_USD_PER_MILLION` and `FOUNDRY_OUTPUT_USD_PER_MILLION` to the rates for your deployment. The console multiplies each step's tokens by those rates. The defaults are a stand-in for a small chat deployment, not a bill from Foundry. After `make start`, open http://127.0.0.1:47821.

Logs go to stderr on the `mission_control` logger. Set `LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. The default is `INFO`. Each line is UTC. While a report is being filed or approved, its id is on those lines. The API key, the filed note, and the model prompts are not logged. Uvicorn writes its own access line as well; the application also logs method, path, status, and duration for `/api` requests.

## What the pipeline does

1. Sort the report with the model. Subsystem and severity have to be in a fixed set. An invalid value falls back to `unknown` and `high`.
2. Set the verdict in code. Wind must be 25 knots or less, temperature 4 C or more, and fuel 98 to 100 percent. A reading on the limit passes. Any miss is `no_go`. The note is not an input to this step.
3. Set the brief-by time in code: 5, 15, or 30 minutes for high, medium, or low. Any limit violation counts as high.
4. Run three model checks at the same time: hidden instructions, missing details, and panic in the tone. A note that tries to instruct the system is flagged and held for a person. It does not change the verdict.
5. Draft a briefing, then review it, up to three rounds. Reviewer feedback is sent into the next draft. Accepting a draft does not approve it.
6. Show one trace row per step with its token counts, and the cost of the report.

## Tool choices

See [docs/tool-choices.md](docs/tool-choices.md).

## Backend responsibilities

The backend is organized by responsibility:

```text
mission_control/
├── main.py                  # Process entry point
├── factory.py               # Composition root and dependency wiring
├── log.py                   # Process logging
├── api/
│   ├── access_log.py        # API request duration and status
│   ├── routes.py            # HTTP decoding and response contracts
│   └── http_errors.py       # Application error to HTTP mapping
├── application/
│   ├── service.py           # Report creation, retrieval, and approval
│   ├── ports.py             # Storage and report-builder protocols
│   ├── pipeline.py          # Model workflow orchestration
│   ├── model_client.py      # Model interface and response types
│   ├── intake.py            # Report input validation
│   ├── prompts.py           # Model prompt construction
│   └── parsing.py           # Model output parsing
├── domain/
│   ├── models.py            # Report types and states
│   ├── errors.py            # Application exceptions
│   ├── limits.py            # Launch limits
│   ├── brief_by.py          # Briefing deadline rules
│   └── cost.py              # Token pricing and cost calculations
└── infrastructure/
    ├── config.py            # Environment configuration
    ├── foundry.py           # Foundry model adapter
    └── repository.py        # SQLite persistence
```

`factory.create_app` wires the concrete dependencies. HTTP routes delegate to
`ReportService`, which depends on the `ReportStore` and `ReportBuilder` protocols.
Application and domain modules do not import HTTP or concrete infrastructure.
`Repository` retains atomic approval transactions. `ReportPipeline` receives its
model and pricing dependencies and keeps execution state local to each call.
The functional `build_report` entry point lives in `application.pipeline`.

Python imports now use these package paths; the process entry point and
`factory.create_app` remain unchanged. HTTP endpoints and payloads are unchanged.
