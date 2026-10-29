# Voice-Based Exam Score Entry for Microsoft Excel

A Windows desktop tool that lets you enter exam candidate data (score,
gender, full name) into an **existing Microsoft Excel workbook** using
voice commands, replacing the manual `Ctrl+F` -> click -> type workflow.

Phase 1 targets Microsoft Excel via `xlwings`. The architecture keeps the
spreadsheet backend behind an interface (`src/spreadsheets/base.py`) so
other backends (e.g. Google Sheets) could be added later without
touching command parsing, validation, or the UI.

## Status

**Stage 1 complete** (foundation): typed command schema, deterministic
parser, candidate lookup, validation rules, a mock Excel backend, and
the orchestration workflow that ties them together - all covered by
automated tests.

**Stage 2 complete** (real Microsoft Excel via xlwings):
`src/spreadsheets/excel.py` connects to an already-open workbook (or
opens one from a configured/explicit path - never creates a new
workbook), reads and verifies headers, reads candidate rows, and
writes confirmed updates straight into Excel cells using the same
`workflow.py` orchestration from Stage 1. Verified against real Excel
application instances (not just mocks).

**Stage 3 complete** (local speech recognition): `src/audio/push_to_talk.py`
captures microphone audio while F8 is held and stops reliably on
release (empty/silent recordings and microphone errors are reported,
never crash); `src/speech/transcriber.py` wraps `faster-whisper` for
local transcription; `src/speech/voice_command.py` chains record ->
transcribe -> parse into one call the future UI will use. Verified
against a real microphone-shaped pipeline and a real `faster-whisper`
model transcribing real synthesized speech, which correctly parsed
into a `SetScoreCommand`. No desktop UI yet (Stage 4).

## Planned end-to-end workflow

1. Open your exam workbook in Microsoft Excel.
2. Launch this application; it connects to the already-open workbook
   (or lets you pick a file) and reads the header row to confirm column
   positions.
3. Hold **F8** and speak a command, e.g.:
   - "Candidate zero zero three zero three, score thirty."
   - "Candidate zero zero three zero three, gender male."
   - "Candidate zero zero three zero three, full name Ally Awadhi."
   - "Find candidate zero zero three zero three."
   - "Find candidate Ally Awadhi."
4. Release F8. The app transcribes your speech locally (faster-whisper),
   parses it into a structured command, and looks up the candidate.
5. If the candidate is found unambiguously and the value is valid, the
   app shows the **old value -> new value** and asks you to confirm.
6. On confirmation, the app writes the value into the correct Excel
   cell and logs the change (timestamp, candidate, cell, old/new value)
   to a local audit log. No raw audio or secrets are ever logged.

Nothing is ever written to the workbook without an exact/unique
candidate match, a passing validation check, and your explicit
confirmation.

## Project structure

```
src/
  audio/          Microphone recording and F8 push-to-talk (Stage 3 - done)
  speech/         Whisper transcription + record->transcribe->parse glue (Stage 3 - done)
  commands/       Command schema + deterministic parser (Stage 1 - done)
  candidates/     Candidate model + safe lookup (Stage 1 - done)
  validation/     Validation rules + audit log (Stage 1 - done)
  spreadsheets/   Backend interface, mock backend (Stage 1), Excel/xlwings backend (Stage 2 - done)
  ui/             Desktop interface (Stage 4)
  config.py       Typed configuration loader
  workflow.py     Orchestration: parse -> lookup -> validate -> confirm -> write
  app.py          Application entry point (added in Stage 4)
scripts/          Dev helper scripts (e.g. synthetic test workbook generator)
tests/            Unit and integration tests
config.json       Non-secret configuration (columns, validation ranges, etc.)
requirements.txt  Dependencies
```

## Configuration (`config.json`)

All values are non-secret and user-editable:

- `excel.workbook_path` / `excel.worksheet_name` - which workbook/sheet
  to use (null = connect to the active open workbook / prompt).
- `excel.header_row` - row containing column headers (default 1).
- `excel.columns` - letters for `registration_number`, `full_name`,
  `gender`, `score` (defaults B, C, D, E per the current workflow).
- `excel.treat_registration_number_as_text` - keeps leading zeros intact.
- `validation.score_min` / `score_max` - inclusive score range (default 0-60).
- `validation.accepted_genders` - map of canonical value -> accepted
  spoken synonyms.
- `speech.whisper_model_size`, `speech.language`, `speech.push_to_talk_key`,
  `speech.sample_rate`.
- `confirmation.require_confirmation` - must stay `true` for the initial
  version per the project requirements.
- `audit_log.path` / `audit_log.store_raw_audio` (audio storage stays
  `false` by default).

The actual column layout, header row, and headers of **your** workbook
are read and verified at connection time (Stage 2) - the above are
just defaults, not assumptions baked into the code.

## Running the tests

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -v
```

All 64 tests pass as of this writing:

- **40 Stage 1** unit/integration tests against the mock Excel backend:
  deterministic parsing of all 5 supported command types and
  reasonable spoken variations (digit-by-digit registration numbers,
  compound number words, "mark"/"sex" synonyms, numeric-digit
  registration numbers, rejection of gibberish/incomplete input);
  candidate lookup (exact match, not-found, ambiguous name matches
  refused rather than guessed, case-insensitive matching, and
  differently-padded registration numbers like `"0303"` vs `"00303"`
  correctly NOT treated as the same candidate); validation (score
  range boundaries, non-numeric scores, gender synonyms, full-name
  sanity checks); and the end-to-end workflow (happy-path score/
  gender/full-name updates, invalid score rejected with nothing
  written, ambiguous/duplicate matches blocking an update, a
  read-only workbook rejecting the write and logging the error while
  leaving the workbook unchanged, and unparseable transcripts never
  triggering a write).
- **5 Stage 2** tests that drive a real, temporary Microsoft Excel
  workbook end-to-end (connecting, reading/verifying headers and
  candidates with leading zeros intact, writing a confirmed update
  and re-reading it from the live cell, a missing workbook, a missing
  worksheet, and a protected worksheet blocking the write) -
  automatically skipped if Excel isn't installed.
- **19 Stage 3** tests: push-to-talk recording against a faked
  microphone/keyboard (start/stop produces the right audio, stopping
  without starting is safe, empty and silent recordings are reported
  as failures rather than silently accepted, a microphone-open
  failure raises a clear error, double-start is a no-op, and a full
  F8 hold-record-release cycle against a simulated key state produces
  audio); Whisper transcription against a faked model (happy path,
  empty audio, silent audio, the model raising during transcription,
  no speech detected, model-load failure, faster-whisper not
  installed); and the record -> transcribe -> parse glue layer
  (happy path producing a `SetScoreCommand`, and each stage's failure
  short-circuiting before the next one runs).

Additionally, the full real pipeline (not mocked) was manually verified
during development: a real `faster-whisper` "base" model loaded and
transcribed real synthesized speech ("Candidate zero zero three zero
three, score thirty.") into text that the deterministic parser turned
into `SetScoreCommand(registration_number='00303', score_text='30.0')`
- end to end, no fakes. This machine has limited free RAM (~0.5-0.9 GB
free out of ~3.8 GB total); the `tiny`/`base` int8 CPU models load and
run fine within that budget, which is why those sizes are the
defaults - larger models (`small`/`medium`) have not been verified
here and may risk out-of-memory on similarly constrained machines.

## Known assumptions to confirm before Stage 4

1. Default columns are B (registration number), C (full name), D
   (gender), E (score), header row 1 - **configurable**, but please
   confirm or correct for your real workbook.
2. Registration numbers are assumed to be spoken digit-by-digit
   ("zero zero three zero three"); mixed formats (e.g. spoken as
   "three oh three" for a padded number) are not yet handled - let us
   know if your registration numbers include letters or are spoken
   differently.
3. Accepted gender synonyms in `config.json` are a starting guess
   ("male"/"m"/"boy"/"man", "female"/"f"/"girl"/"woman") - adjust to
   match your actual data and terminology.
4. Score range defaults to 0-60 inclusive, per the project description.
5. The deterministic parser requires the literal keyword "candidate"
   (or "find candidate") to appear - please confirm this matches how
   you intend to speak commands, since no LLM-based intent detection is
   used in this version.
6. When multiple workbooks are open in Excel simultaneously and
   `excel.workbook_path` isn't set, the app refuses to guess which one
   you mean and asks you to either close the extras or set the path
   explicitly - confirm this is the behaviour you want, versus e.g.
   always preferring the active window.
7. `whisper_model_size` defaults to `"base"` in config.json. On this
   development machine RAM is tight, so `"tiny"` or `"base"` are the
   safe choices; if your real machine has more free memory you may
   prefer `"small"` for better accuracy, but that hasn't been tested
   here yet.
8. The `keyboard` package's global F8 hook was verified to work without
   running as Administrator on this machine, but some Windows/security
   software configurations can restrict global keyboard hooks - let us
   know if F8 doesn't register during Stage 4 testing on your machine.

## Next steps (not yet implemented)

- **Stage 4**: Simple desktop UI showing the workbook/worksheet in use,
  push-to-talk status, transcript, parsed command, candidate found,
  proposed update, confirm/cancel controls, success/error messages, and
  recent operations history.
- **Stage 5**: Full workflow testing (including the real exam
  workbook, once provided) and polished install/launch instructions.
