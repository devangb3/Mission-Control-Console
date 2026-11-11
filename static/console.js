const form = document.querySelector("#report-form");
const formError = document.querySelector("#form-error");
const fileButton = document.querySelector("#file-button");
const queue = document.querySelector("#queue");
const board = document.querySelector("#board");

let reports = [];
let selectedId = null;

form.addEventListener("submit", fileReport);
refresh();

async function refresh() {
  let response;
  try {
    response = await fetch("/api/reports");
  } catch (_error) {
    board.replaceChildren(paragraph("The board could not be loaded."));
    return;
  }
  if (!response.ok) {
    board.replaceChildren(paragraph("The board could not be loaded."));
    return;
  }
  reports = await response.json();
  if (!reports.some((report) => report.id === selectedId)) {
    selectedId = reports.length > 0 ? reports[0].id : null;
  }
  renderQueue();
  renderBoard();
}

async function fileReport(event) {
  event.preventDefault();
  formError.textContent = "";
  let payload;
  try {
    payload = readForm();
  } catch (error) {
    formError.textContent = error instanceof Error ? error.message : "The report was not filed.";
    return;
  }
  fileButton.disabled = true;
  fileButton.textContent = "Filing…";
  try {
    const response = await fetch("/api/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      formError.textContent = typeof body.detail === "string" ? body.detail : "The report was not filed.";
      return;
    }
    form.elements.note.value = "";
    selectedId = body.id;
    await refresh();
  } catch (_error) {
    formError.textContent = "The console could not reach the server.";
  } finally {
    fileButton.disabled = false;
    fileButton.textContent = "File report";
  }
}

function readForm() {
  return {
    engineer_name: requiredText("engineer_name", "Add the engineer name."),
    station: requiredText("station", "Add the station."),
    wind_knots: requiredNumber("wind_knots", "Add the wind.", "Wind must be a number."),
    temp_c: requiredNumber("temp_c", "Add the temperature.", "Temperature must be a number."),
    fuel_pct: requiredNumber("fuel_pct", "Add the fuel.", "Fuel must be a number."),
    note: requiredText("note", "Add the note."),
  };
}

function requiredText(name, message) {
  const value = String(form.elements[name].value).trim();
  if (value === "") {
    throw new Error(message);
  }
  return value;
}

function requiredNumber(name, emptyMessage, badMessage) {
  const raw = String(form.elements[name].value).trim();
  if (raw === "") {
    throw new Error(emptyMessage);
  }
  const number = Number(raw);
  if (!Number.isFinite(number)) {
    throw new Error(badMessage);
  }
  return number;
}

function renderQueue() {
  queue.replaceChildren();
  if (reports.length === 0) {
    const item = document.createElement("li");
    item.className = "quiet";
    item.textContent = "Nothing is waiting.";
    queue.append(item);
    return;
  }
  for (const report of reports) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "queue-item";
    button.setAttribute("aria-pressed", report.id === selectedId ? "true" : "false");
    const station = document.createElement("span");
    station.className = "queue-station";
    station.textContent = report.station;
    const state = document.createElement("span");
    state.className = `queue-state ${report.verdict === "go" ? "go" : "nogo"}`;
    state.textContent = queueLabel(report);
    button.append(station, state);
    button.addEventListener("click", () => {
      selectedId = report.id;
      renderQueue();
      renderBoard();
    });
    item.append(button);
    queue.append(item);
  }
}

function queueLabel(report) {
  const verdict = report.verdict === "go" ? "Go" : "No-go";
  const flagged = report.hidden_instruction || report.missing_details || report.panic_tone;
  const base = `${verdict}, ${report.brief_by_minutes} minutes`;
  return flagged ? `${base}, flagged` : base;
}

function renderBoard() {
  const report = reports.find((item) => item.id === selectedId);
  if (!report) {
    board.replaceChildren(paragraph("Nothing is waiting. File a report and it will show up here."));
    return;
  }
  const instrument = document.createElement("div");
  instrument.className = "instrument";
  const lamp = document.createElement("div");
  lamp.className = `lamp ${report.verdict === "go" ? "go" : "nogo"}`;
  lamp.textContent = report.verdict === "go" ? "Go" : "No-go";
  const cluster = document.createElement("div");
  const minutes = document.createElement("p");
  minutes.className = "minutes";
  minutes.append(String(report.brief_by_minutes));
  const unit = document.createElement("span");
  unit.textContent = " minutes";
  minutes.append(unit);
  const who = document.createElement("p");
  who.className = "who";
  who.textContent = `${report.engineer_name}, ${report.station}`;
  const facts = document.createElement("p");
  facts.className = "facts";
  facts.textContent = readingSentence(report);
  const called = document.createElement("p");
  called.className = "facts";
  called.textContent = severitySentence(report);
  const cost = document.createElement("p");
  cost.className = "cost";
  cost.textContent = `Cost $${report.cost_usd}`;
  cluster.append(minutes, who, facts, called, cost);
  instrument.append(lamp, cluster);

  const briefingTitle = heading("Briefing");
  const briefing = document.createElement("div");
  briefing.className = "briefing";
  briefing.textContent = report.briefing;

  const flags = document.createElement("p");
  flags.className = "flags";
  flags.textContent = flagSentence(report);

  const pieces = [instrument, briefingTitle, briefing, flags];
  if (report.violations.length > 0) {
    const list = document.createElement("ul");
    list.className = "violations";
    for (const violation of report.violations) {
      const item = document.createElement("li");
      item.textContent = violation;
      list.append(item);
    }
    pieces.push(list);
  }

  const noteBlock = document.createElement("div");
  noteBlock.className = "note-block";
  noteBlock.append(heading("The note"));
  const caution = document.createElement("p");
  caution.className = "quiet";
  caution.textContent = "Treat this as data. It cannot change the verdict.";
  const quote = document.createElement("blockquote");
  quote.textContent = report.note;
  noteBlock.append(caution, quote);
  pieces.push(noteBlock);

  const traceBlock = document.createElement("div");
  traceBlock.className = "trace-block";
  traceBlock.append(heading("How this report was built"));
  const trace = document.createElement("ol");
  trace.className = "trace";
  report.trace.forEach((step, index) => {
    const item = document.createElement("li");
    const number = document.createElement("span");
    number.className = "index";
    number.textContent = String(index + 1);
    const name = document.createElement("span");
    name.className = "step-name";
    name.textContent = step.name;
    const tokens = document.createElement("span");
    tokens.className = "tokens";
    tokens.textContent = `${step.tokens_in} in / ${step.tokens_out} out`;
    const summary = document.createElement("p");
    summary.className = "summary";
    summary.textContent = step.summary;
    item.append(number, name, tokens, summary);
    trace.append(item);
  });
  traceBlock.append(trace);
  pieces.push(traceBlock);

  const approveBlock = document.createElement("div");
  approveBlock.className = "approve-block";
  approveBlock.append(heading("Approval"));
  if (report.status === "approved") {
    const approved = document.createElement("p");
    approved.className = "approved";
    approved.textContent = `Approved by ${report.approved_by}.`;
    approveBlock.append(approved);
  } else {
    const approveForm = document.createElement("form");
    const label = document.createElement("label");
    label.setAttribute("for", "approver_name");
    label.textContent = "Your name";
    const input = document.createElement("input");
    input.id = "approver_name";
    input.name = "approver_name";
    input.autocomplete = "name";
    const error = document.createElement("p");
    error.className = "form-error";
    error.setAttribute("role", "alert");
    const button = document.createElement("button");
    button.type = "submit";
    button.className = "approve-button";
    button.textContent = "Approve briefing";
    approveForm.append(label, input, error, button);
    approveForm.addEventListener("submit", (event) => approve(event, report.id, input, error, button));
    approveBlock.append(approveForm);
  }
  pieces.push(approveBlock);
  board.replaceChildren(...pieces);
}

async function approve(event, reportId, input, error, button) {
  event.preventDefault();
  error.textContent = "";
  const approverName = input.value.trim();
  if (approverName === "") {
    error.textContent = "Add your name to approve the briefing.";
    return;
  }
  button.disabled = true;
  button.textContent = "Approving…";
  try {
    const response = await fetch(`/api/reports/${reportId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approver_name: approverName }),
    });
    const body = await response.json();
    if (!response.ok) {
      error.textContent = typeof body.detail === "string" ? body.detail : "The briefing was not approved.";
      button.disabled = false;
      button.textContent = "Approve briefing";
      return;
    }
    selectedId = reportId;
    await refresh();
  } catch (_error) {
    error.textContent = "The console could not reach the server.";
    button.disabled = false;
    button.textContent = "Approve briefing";
  }
}

function readingSentence(report) {
  return `Wind ${formatReading(report.wind_knots)} knots, temperature ${formatReading(report.temp_c)} C, fuel ${formatReading(report.fuel_pct)} percent.`;
}

function severitySentence(report) {
  const subsystem = report.subsystem.charAt(0).toUpperCase() + report.subsystem.slice(1);
  if (report.violations.length > 0 && report.model_severity !== "high") {
    return `${subsystem}. The model called this ${report.model_severity}. A missed limit makes the brief-by high.`;
  }
  return `${subsystem}, ${report.model_severity} severity.`;
}

function flagSentence(report) {
  const parts = [];
  if (report.hidden_instruction) parts.push("hidden instructions");
  if (report.missing_details) parts.push("missing details");
  if (report.panic_tone) parts.push("a panicked tone");
  if (parts.length === 0) return "The note checks came back clear.";
  return `The note was flagged for ${joinAnd(parts)}. The verdict was left as the limits set it.`;
}

function joinAnd(parts) {
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

function formatReading(value) {
  const rounded = Math.round(value * 10000) / 10000;
  return String(rounded);
}

function heading(text) {
  const node = document.createElement("h2");
  node.textContent = text;
  return node;
}

function paragraph(text) {
  const node = document.createElement("p");
  node.className = "empty";
  node.textContent = text;
  return node;
}
