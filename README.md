# Mission Control

Meridian Launch Services is 90 minutes from a launch. An engineer files an anomaly with a name, a station, three readings, and a note. The console sorts the note, checks the launch limits in code, drafts a briefing, and waits. Only a person can approve it.

The model is a deployment in Microsoft Foundry, called through one client. Tests use a fake of that client, so they need no network and no API key.

## Commands

Start the app:

```
make start
```

Run the tests:

```
make test
```

`make start` loads `.env` from the repo root. Copy `.env.example` to `.env` and set the Foundry resource URL, API key, and deployment name. The client calls `{resource}/openai/v1/chat/completions` and sends the key as a bearer token. That is the current Foundry route. The Azure AI Inference SDK retired on 26 August 2026.

Set `FOUNDRY_INPUT_USD_PER_MILLION` and `FOUNDRY_OUTPUT_USD_PER_MILLION` to the rates for your deployment. The console multiplies each step's tokens by those rates. The defaults are a stand-in for a small chat deployment, not a bill from Foundry. After `make start`, open http://127.0.0.1:47821.

## What the pipeline does

1. Sort the report with the model. Subsystem and severity have to be in a fixed set. An invalid value falls back to `unknown` and `high`.
2. Set the verdict in code. Wind must be 25 knots or less, temperature 4 C or more, and fuel 98 to 100 percent. A reading on the limit passes. Any miss is `no_go`. The note is not an input to this step.
3. Set the brief-by time in code: 5, 15, or 30 minutes for high, medium, or low. Any limit violation counts as high.
4. Run three model checks at the same time: hidden instructions, missing details, and panic in the tone. A note that tries to instruct the system is flagged and held for a person. It does not change the verdict.
5. Draft a briefing, then review it, up to three rounds. Reviewer feedback is sent into the next draft. Accepting a draft does not approve it.
6. Show one trace row per step with its token counts, and the cost of the report.

## Tool choices

See [docs/tool-choices.md](docs/tool-choices.md).
