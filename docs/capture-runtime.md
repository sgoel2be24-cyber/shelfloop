# Capture runtime and verified support

Checked locally on 25 October 2026. Capture never commits a model/OCR proposal:
the owner must review the exact catalogue product and whole sealed-pack count.

## Available now

- Text entry supports English, Hindi digits, common Hindi/transliterated count
  words, product aliases and multiple product clauses.
- TXT and CSV invoice uploads work locally. CSV headers `product`/`item`/
  `description` and `quantity`/`qty` identify the fields; unrecognised columns
  remain reviewable text instead of guessed fields.
- Text PDFs work through the required `pypdf` dependency. Scanned/image-only
  PDF pages are not OCR-processed by this path.
- Uploads are limited to 8 MiB, text to 20,000 characters, and PDF invoices to
  ten pages. Password-protected PDFs are rejected.
- Confident rule results do not wait for the optional language model. A missing
  Ollama server is retried after a 30-second cooldown rather than delaying each
  capture. Model suggestions, if present, are labelled suggestions only.
- Confirmation rejects unknown products, unresolved counts, fractions,
  negative/duplicate indices, invalid kinds, weight/volume counts and counts
  above one million packs. It is atomic and idempotency-aware.
- New captured stock is private (`permit_share=0`) and has an unknown cost
  sentinel (`cost_paise=0`) and unknown date. These are not estimates. Review
  lot details before making it available to the exchange planner.

## Runtime status and honest limits

Inspect `/api/health` under `capture_capabilities`, or from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'backend'); from app.capture_media import capabilities; import json; print(json.dumps(capabilities(),indent=2))"
```

The inspected project virtual environment has `pypdf 6.21.2`. The checked local
machine has no Tesseract installation in PATH, Program Files, Program Files
(x86), or the per-user Programs location. The project virtual environment has
no Faster-Whisper package and no cached multilingual `small` model.

A pre-existing `Systran/faster-whisper-small.en` cache is present. It is an
**English-only** model and is deliberately not advertised as Hindi support.
Image OCR and local speech currently return a specific unavailable status and
manual-entry fallback. Those engines have not been runtime-validated here.

Browser speech recognition is browser-dependent, may use a remote service,
and must not be described as guaranteed offline speech. It is separate from
the optional local audio-upload engine below.

## Optional local image OCR

Install Tesseract using its [installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html).
Make English (`eng`) and Hindi (`hin`) trained data available to that installation.
Verify language data with the actual executable:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

The adapter checks PATH and the standard Windows installation locations. For
a different path, set this variable **before** starting the backend:

```powershell
$env:SHELFLOOP_TESSERACT = "D:\Tools\Tesseract-OCR\tesseract.exe"
```

Supported image uploads are PNG, JPEG and WebP with matching content signatures.
OCR uses the locally installed English/Hindi data, a 30-second process timeout,
and the same owner-review gate. A filename or MIME type alone is not trusted.
Installing the binary does not establish OCR accuracy; run a held-out invoice
test and record the language/quantity errors before claiming support.

## Optional local Hindi/English audio transcription

This setup is optional and requires a one-time package/model download; there
is no paid service. Do not add it to an automated launcher that unexpectedly
downloads a large model.

From the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install faster-whisper
.\backend\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small', local_dir='models/faster-whisper-small')"
$env:SHELFLOOP_WHISPER_MODEL_DIR = (Resolve-Path "models/faster-whisper-small").Path
```

Restart the backend with that environment. The engine also recognises existing
multilingual `small` snapshots in the normal Hugging Face cache. Runtime model
loading uses `local_files_only=True`; it will not automatically download a
model when an owner uploads a recording.

The adapter uses CPU INT8 inference. It incrementally decodes at most 60 seconds
at 16 kHz and supports WAV, WebM, OGG, MP3 and M4A/MP4 audio files. Transcription
is still a proposal: verify brand names, pack size and numbers before confirming.

Verify with real Hindi, English and code-switched recordings, including silence,
background noise, ambiguous SKUs and spoken quantities. Tests with a mocked
engine do not establish microphone or transcription accuracy.

Reference: [Faster-Whisper repository](https://github.com/SYSTRAN/faster-whisper).

## Optional Ollama suggestions

If Ollama and the configured `qwen3:4b` model are already installed, its local
generate endpoint can enrich unresolved text captures with suggestions. No API
key is required for local inference. Keep the model warm for interactive use;
the capture path intentionally has a short timeout and a missing-server cooldown.
It neither accepts model-invented catalogue records nor lets model output approve
or commit a capture.

Reference: [Ollama local API](https://docs.ollama.com/api/introduction).

## Verification commands

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_capture.py tests/test_capture_regressions.py -q --basetemp .pytest-tmp-capture-check
Pop-Location
```

The capture regression suite includes real generated text-PDF extraction, real
CSV uploads through the API, price/pack-size separation, Indic quantities,
atomic invalid-input rejection, concurrent retry protection and explicit
unavailable-engine responses. It does not assert that optional OCR, local
speech, or Ollama are installed or field-validated.
