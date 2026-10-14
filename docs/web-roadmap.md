# Path to an interactive web interface

This document is an engineering roadmap, not part of canonical Onto4
semantics. The goal is a web interface in which users can connect their own
language model and complete the clarification and assessment workflow without
turning that model into the authority for `T/F/U/C` verdicts.

## User journey

A user opens the web interface, selects a provider profile and asks a question.
If the formulation admits several readings, the interface presents a
clarification question. After the answer, the system explicitly starts a new
formalization and assessment pass for the successor interpretation snapshot.

The result should expose its basis instead of showing only a verdict:

```text
user question
    ↓
interpretation space
    ↓
clarification, when needed
    ↓
formalization candidates
    ↓
deterministic Onto4 assessment
    ↓
T / F / U / C, evidence and alternative readings
```

This is not a conventional chat in which a language model directly writes the
answer. Interpretation, formalization, clarification transition, assessment
and verdict remain separate operations.

## Starting point

The repository already contains the deterministic core,
`InterpretationProvider` and `FormalizationProvider` boundaries, typed
clarification machinery and a `ReasoningSession` with explicit reassessment.
Model-backed adapters, an HTTP API and a web interface are not yet a complete
user journey. The stages below add them one at a time so that transport and
model failures do not hide orchestration failures.

## Connecting a user-supplied model

The first supported protocol is an OpenAI-compatible API. A minimal provider
profile contains:

```text
name
protocol = openai-compatible
base_url
model
authentication = none | bearer
```

Authentication is not labelled as a password: the first slice supports no
authentication and Bearer tokens. Custom headers and provider-native APIs can
be added later when a demonstrated use case cannot be expressed through the
initial contract.

A profile may point to either a local or remote endpoint:

```text
http://127.0.0.1:8080/v1
https://llm.example.org/v1
```

The identity of a particular model is not part of Onto4 semantics. Endpoint,
protocol, model name and credentials are infrastructure configuration connected
to the existing `InterpretationProvider` and `FormalizationProvider`
boundaries.

The first UI may use one profile for both roles. Separate interpretation,
formalization and result-rendering models can later appear under advanced
settings without changing the core contract.

## Model authority boundary

A language model may propose:

- an `InterpretationSpace`;
- `FormalizationCandidate[]`;
- a human-readable explanation of an already computed result.

It does not authoritatively return `T/F/U/C`. Candidates pass schema and
provenance validation before the deterministic core computes a verdict:

```text
Provider profile
    ↓
InterpretationProvider
    ↓
InterpretationSpace
    ↓
FormalizationProvider
    ↓
FormalizationCandidate[]
    ↓
Onto4 core
    ↓
ReasoningSession
    ↓
clarification or T / F / U / C
```

Neither a provider nor the web interface may replace the core's decision.

## Two connection modes

### Onto4 HTTP runtime

The primary path to a complete vertical slice keeps the Python core:

```text
Browser
    ↓
Onto4 HTTP API
    ↓
Python Onto4
    ↓
user-supplied LLM endpoint
```

The selected Onto4 runtime receives the model endpoint and credentials for the
current session. The first working runtime is assumed to be local or
self-hosted, so the user explicitly trusts it with the token. A shared public
runtime must not accept third-party credentials without a separate trust,
security and retention model.

### Direct browser connection

A static site may call the user's endpoint without an Onto4 server:

```text
GitHub Pages
    ↓
user browser
    ↓
user-supplied LLM endpoint
```

This mode is a separate experiment. It requires:

- an endpoint that permits CORS requests;
- browser support for calls from a public HTTPS origin to `localhost` or a
  private network;
- a way to execute the deterministic Onto4 core in the browser instead of
  replacing it with a model response.

Direct connection is therefore useful for transport and provider-profile
experiments, but is not a complete Onto4 workflow until the core is available
in a browser runtime.

## Credential handling

A static frontend does not receive secrets from GitHub Actions or repository
secrets. A secret injected into HTML or JavaScript at build time is available
to site visitors.

By default:

- `base_url`, protocol and model may be stored locally as a profile;
- a Bearer token lives only in memory for the current tab;
- closing the tab removes the token;
- persistent token storage requires separate explicit consent and is outside
  the first release;
- logs and error messages must not contain credentials.

The UI states where a token will be sent. In direct-browser mode it goes only
to the configured endpoint. In Onto4 HTTP runtime mode it is sent to the
selected runtime, so that trust boundary must be visible before a session
starts.

## Implementation and experiment sequence

### 1. OpenAI-compatible provider contract

- introduce a typed `ProviderProfile`;
- support `none` and `bearer` authentication;
- implement a connection test;
- keep credentials out of fixtures, logs and errors;
- define request timeout and response-size limits.

### 2. Model-backed interpretation and formalization

- implement separate OpenAI-compatible adapters for `InterpretationProvider`
  and `FormalizationProvider`;
- require structured output and validate it fail-closed;
- preserve conceptual-depth, reading, assumption and candidate provenance;
- do not connect the model to deterministic `T/F/U/C` computation.

### 3. Minimal Onto4 HTTP API

- expose reasoning-session creation, pending clarification answers and explicit
  reassessment;
- preserve the existing `ReasoningSession` exact-snapshot provenance;
- do not reassess automatically after an answer;
- keep provider profiles at the session boundary, outside Onto4 semantic
  context.

### 4. Minimal static web interface

- add `apps/onto4-web`;
- let the user configure the Onto4 runtime, LLM `base_url`, model and
  authentication;
- add `Test connection`;
- store profiles without credentials;
- surface CORS, mixed-content, timeout and unavailable-endpoint errors.

### 5. Interactive `ReasoningSession`

- show pending clarifications and allowed answers;
- show the transition to a successor snapshot after an answer;
- make reassessment a separate explicit workflow action;
- display landscape, verdict, Evidence4 and alternative readings without
  conflating those levels.

### 6. Direct-browser experiment

- test CORS-enabled OpenAI-compatible endpoints on `localhost` and remote HTTPS
  origins;
- select a way to run the Python core in the browser or provide an equivalent,
  verifiable runtime;
- compare it with the HTTP API using the same fixture scenarios;
- mark it supported only after the complete workflow, rather than a single
  model call, has been verified.

### 7. Provider expansion and operational protection

- add custom headers and native protocols in response to real use cases;
- permit distinct profiles for interpretation, formalization and rendering;
- add rate limits, input/output limits, timeouts, a model allowlist, daily
  budgets and abuse protection to any public hosted runtime;
- handle persistence and session versioning separately from the initial UI.

## First complete release criterion

The first complete web slice is ready when a user can connect an
OpenAI-compatible model, ask a natural-language question, answer a fixed
clarification and receive the result of a new explicit assessment pass. The
credential is not stored by default, the model does not issue an Onto4 verdict,
and every transition remains bound to the exact interpretation snapshot.
