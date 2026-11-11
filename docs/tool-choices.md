# Tool choices

Meridian needs a console that is up for the last 90 minutes of a countdown, on one machine, with a verdict that a note cannot talk its way out of.

## Back end

Python and FastAPI.

The limit check, the brief-by clock, and the cost math sit in the same process as the request that files a report. One language holds the rules and the tests that pin the boundaries.

Rejected alternative: a Node service in front of a separate Python worker. That splits the verdict from the request that has to return it, and it gives the countdown two processes to keep alive.

Customer concern: if the model is slow or wrong, the flight director still receives the verdict the readings produced. A crash has to fail the filing with a clear message rather than store a half-written go.

## Front end

One console page, HTML, CSS, and JavaScript, served by the same process.

The flight director reads a lamp, a brief-by time, the briefing, and a trace. The page is the whole interface, and `make start` brings it up with the API.

Rejected alternative: a separate React dev server. The start command would be two processes, and a refresh during the countdown would depend on both of them.

Customer concern: the verdict has to be readable at a glance, and the original note has to stay on the board as data, not as instructions.

## Database

SQLite, one file under `data/`.

A report is written in a single insert after the pipeline finishes. Opening that file in a new process is the restart. There is no second service to connect to.

Rejected alternative: Postgres. It is the right database for a shared control room later, and the wrong one for a single console that has to come back after a process restart without a database host.

Customer concern: a report filed before a restart is still on the board when the process comes back. Losing the queue at T-90 is the failure Meridian cannot take.

## Model

Microsoft Foundry, through the OpenAI v1 chat-completions route on the Foundry resource (`https://<resource>.openai.azure.com/openai/v1/`). Every step calls the same `ModelClient`. The deployment name is configuration, not a branch in the pipeline.

Rejected alternative: the Azure AI Inference SDK and the `/models` route. Microsoft retired that SDK on 26 August 2026 and tells new apps to use the v1 route. Calling the SDK from each pipeline step was the other reject: a test could not replace "the model" in one place, and a hidden instruction would have more than one function to confuse.

Customer concern: a note that tells the system to set the verdict to go must not be able to. The verdict function does not take the note. Tests run with a fake client, with no API key and no network, because a countdown check cannot depend on Foundry being reachable.
