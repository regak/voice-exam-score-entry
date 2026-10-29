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
application instances (not just mocks) - see "Running the tests"
below. No speech recognition or UI yet (Stages 3-4).

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
  audio/          Microphone recording and F8 push-to-talk (Stage 3)
  speech/         Whisper transcription (Stage 3)
  commands/       Command schema + deterministic parser (Stage 1 - done)
  candidates/     Candidate model + safe lookup (Stage 1 - done)
  validation/     Validation rules + audit log (Stage 1 - done)
  spreadsheets/   Backend interface, mock backend (Stage 1), Excel/xlwings backend (Stage 2)
  ui/             Desktop interface (Stage 4)
  config.py       Typed configuration loader
  workflow.py     Orchestration: parse -> lookup -> validate -> confirm -> write
  app.py          Application entry point (added in later stages)
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
are read and verified at connection time in Stage 2 - the above are
just defaults, not assumptions baked into the code.

## Running the tests (Stage 1)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -v
```

All 45 tests pass as of this writing (40 Stage 1 unit/integration
tests against the mock backend, plus 5 Stage 2 tests that drive a
real, temporary Microsoft Excel workbook end-to-end and are
automatically skipped if Excel isn't installed):

- Deterministic parsing of all 5 supported command types and reasonable
  spoken variations (digit-by-digit registration numbers, compound
  number words, "mark"/"sex" synonyms, numeric-digit registration
  numbers), plus rejection of gibberish/incomplete input.
- Candidate lookup: exact registration match, not-found, ambiguous name
  matches (refuses to guess), case-insensitive name matching, and the
  distinction between differently-padded registration numbers (e.g.
  `"0303"` vs `"00303"` are NOT treated as the same candidate).
- Validation: score range boundaries, non-numeric scores, gender
  synonyms/canonicalization, full-name sanity checks.
- End-to-end workflow against a mock Excel backend: happy-path score/
  gender/full-name updates, invalid score rejected with nothing
  written, ambiguous name lookup blocking an update, duplicate
  registration numbers blocking an update, a read-only workbook
  rejecting the write and logging the error while leaving the
  workbook unchanged, and unparseable transcripts never triggering a
  write.
- Stage 2: connecting to a real Microsoft Excel workbook (both when
  it's already open and when it must be opened from a configured
  path), reading/verifying headers and candidate rows with leading
  zeros intact, writing a confirmed score update into a live workbook
  and re-reading it back from the cell, a missing workbook path, a
  missing worksheet name, and a protected worksheet blocking the write
  (with the workbook left unchanged and the error audit-logged).

## Known assumptions to confirm before Stage 3

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

## Next steps (not yet implemented)

- **Stage 3**: Local `faster-whisper` transcription plus F8
  push-to-talk audio capture.
- **Stage 4**: Simple desktop UI (transcript, parsed command, candidate,
  proposed change, confirm/cancel, history).
- **Stage 5**: Full workflow testing and polished install/launch
  instructions.
