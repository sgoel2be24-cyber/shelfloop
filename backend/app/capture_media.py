"""Bounded local media extraction; never downloads a model or calls a cloud API.

Extraction produces text for the ordinary proposal/confirmation pipeline. It
never writes inventory. Optional engines report their absence explicitly.
"""
from functools import lru_cache
import csv
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_AUDIO_SECONDS = 60
MAX_TEXT_CHARS = 20_000


class CaptureMediaError(ValueError):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _tesseract_path() -> str | None:
    configured = os.environ.get("SHELFLOOP_TESSERACT")
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    for root in (os.environ.get("PROGRAMFILES", "C:/Program Files"),
                 os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"),
                 str(Path.home() / "AppData/Local/Programs")):
        executable = Path(root) / "Tesseract-OCR/tesseract.exe"
        if executable.is_file():
            return str(executable)
    return None


def _whisper_model_path() -> str | None:
    configured = os.environ.get("SHELFLOOP_WHISPER_MODEL_DIR")
    if configured and (Path(configured) / "model.bin").is_file():
        return str(Path(configured).resolve())
    # Only inspect the known faster-whisper-small cache; never fetch missing files.
    hub = Path(os.environ.get("HF_HUB_CACHE", Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"))
    for repository in ("models--Systran--faster-whisper-small", "models--guillaumekln--faster-whisper-small"):
        snapshots = hub / repository / "snapshots"
        if snapshots.is_dir():
            for model in sorted(snapshots.iterdir(), reverse=True):
                if (model / "model.bin").is_file():
                    return str(model)
    return None


def capabilities() -> dict:
    speech_library = _has_module("faster_whisper")
    speech_cache = _whisper_model_path() is not None
    return {
        "text_invoice": {"available": True, "extensions": ["txt", "csv"]},
        "pdf_invoice": {"available": _has_module("pypdf"), "max_pages": MAX_PDF_PAGES,
                        "note": "Text PDFs only; scanned pages require local OCR."},
        "image_ocr": {"available": _tesseract_path() is not None,
                      "note": "Requires local Tesseract; English/Hindi depend on installed language data."},
        "local_speech": {"available": speech_library and speech_cache,
                         "library_installed": speech_library, "model_cached": speech_cache,
                         "max_seconds": MAX_AUDIO_SECONDS,
                         "note": "Optional Faster-Whisper small; local files only, no automatic downloads."},
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }


def _validate_data(data: bytes):
    if not isinstance(data, bytes) or not data:
        raise CaptureMediaError("Upload an invoice or a short audio recording.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CaptureMediaError("Upload is larger than the 8 MiB limit.", "too_large")


def _text_result(text: str, engine: str, warnings: list[str] | None = None) -> dict:
    text = text.replace("\x00", "").strip()
    if len(text) > MAX_TEXT_CHARS:
        raise CaptureMediaError("Extracted text exceeds 20,000 characters; upload fewer items.", "too_large")
    if not text:
        raise CaptureMediaError("No readable text was found. Enter the items manually or upload a clearer document.")
    return {"text": text, "engine": engine,
            "warnings": ["Review product, pack size and quantity before confirming.", *(warnings or [])]}


def extract_invoice(data: bytes, filename: str, content_type: str = "") -> dict:
    """Extract TXT/CSV, text PDF or image text without trusting MIME alone."""
    _validate_data(data)
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".txt", ".csv"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise CaptureMediaError("Text invoices must use UTF-8 encoding.") from None
        if len(text) > MAX_TEXT_CHARS:
            raise CaptureMediaError("Invoice text exceeds 20,000 characters; upload fewer items.", "too_large")
        if suffix == ".csv":
            rows = list(csv.reader(io.StringIO(text)))
            if rows:
                headers = [cell.strip().casefold() for cell in rows[0]]
                product_col = next((i for i, value in enumerate(headers)
                                    if value in {"product", "item", "description", "product_name"}), None)
                qty_col = next((i for i, value in enumerate(headers)
                                if value in {"qty", "quantity", "packs", "packets"}), None)
                if product_col is not None and qty_col is not None:
                    lines = []
                    for row in rows[1:]:
                        if not any(cell.strip() for cell in row):
                            continue
                        if len(row) <= max(product_col, qty_col):
                            raise CaptureMediaError("CSV rows must include the product and quantity columns.")
                        lines.append(f"{row[product_col].strip()} {row[qty_col].strip()} packs")
                    return _text_result("\n".join(lines), "csv-invoice")
            return _text_result(text, "text-invoice", ["CSV column roles were not recognised; confirm all quantities manually."])
        return _text_result(text, "text-invoice")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise CaptureMediaError("The uploaded file is not a valid PDF.")
        if not _has_module("pypdf"):
            raise CaptureMediaError("Local PDF extraction is not installed. Use a UTF-8 text invoice or manual entry.", "unavailable")
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise CaptureMediaError("Encrypted PDFs are not supported; use an unlocked invoice copy.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise CaptureMediaError("Upload at most 10 invoice pages.", "too_large")
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
                if sum(map(len, parts)) > MAX_TEXT_CHARS:
                    raise CaptureMediaError("Extracted invoice is too long.", "too_large")
            return _text_result("\n".join(parts), "pypdf",
                                ["Blank/scanned pages are not OCR-processed in the PDF path."])
        except CaptureMediaError:
            raise
        except Exception as exc:
            raise CaptureMediaError("The PDF could not be read. Try a text invoice or manual entry.") from exc
    image_types = {
        ".png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": lambda b: b.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
        ".webp": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP",
    }
    if suffix not in image_types:
        raise CaptureMediaError("Use a TXT, CSV, PDF, PNG, JPEG or WebP invoice.")
    if not image_types[suffix](data):
        raise CaptureMediaError("Image contents do not match the supported invoice format.")
    executable = _tesseract_path()
    if not executable:
        raise CaptureMediaError("Local image OCR is not installed. Use a text/PDF invoice or manual entry.", "unavailable")
    try:
        languages = subprocess.run([executable, "--list-langs"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=10, check=True)
        available = set(languages.stdout.splitlines())
        selected = [lang for lang in ("eng", "hin") if lang in available]
        if not selected:
            raise CaptureMediaError("Tesseract needs English or Hindi language data installed locally.", "unavailable")
        with tempfile.TemporaryDirectory(prefix="shelfloop-ocr-") as folder:
            source = Path(folder) / ("invoice" + suffix)
            source.write_bytes(data)
            result = subprocess.run([executable, str(source), "stdout", "-l", "+".join(selected), "--psm", "6"],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=30, check=True)
        return _text_result(result.stdout, "tesseract", ["Installed OCR languages: " + ", ".join(selected)])
    except CaptureMediaError:
        raise
    except (subprocess.SubprocessError, OSError) as exc:
        raise CaptureMediaError("Local OCR failed or timed out. Try a clearer invoice or manual entry.") from exc


@lru_cache(maxsize=1)
def _speech_model(path: str):
    from faster_whisper import WhisperModel
    return WhisperModel(path, device="cpu", compute_type="int8", local_files_only=True)


def _decode_bounded_audio(source: Path):
    """Decode incrementally so a compressed upload cannot expand without a bound."""
    import av
    import numpy as np
    chunks, samples = [], 0
    with av.open(str(source)) as container:
        if container.duration and container.duration / av.time_base > MAX_AUDIO_SECONDS:
            raise CaptureMediaError("Record at most 60 seconds of audio.", "too_large")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for output in resampler.resample(frame):
                array = output.to_ndarray().reshape(-1)
                samples += array.size
                if samples > MAX_AUDIO_SECONDS * 16000:
                    raise CaptureMediaError("Record at most 60 seconds of audio.", "too_large")
                chunks.append(array)
        for output in resampler.resample(None):
            array = output.to_ndarray().reshape(-1)
            samples += array.size
            if samples > MAX_AUDIO_SECONDS * 16000:
                raise CaptureMediaError("Record at most 60 seconds of audio.", "too_large")
            chunks.append(array)
    if not chunks:
        raise CaptureMediaError("The recording contains no readable audio.")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def transcribe_audio(data: bytes, filename: str, content_type: str = "") -> dict:
    _validate_data(data)
    suffix = Path(filename or "").suffix.lower()
    magic_ok = (data.startswith(b"RIFF") and data[8:12] == b"WAVE" or
                data.startswith((b"OggS", b"ID3", b"\x1aE\xdf\xa3")) or
                len(data) > 12 and data[4:8] == b"ftyp" or
                len(data) > 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    if suffix not in {".wav", ".webm", ".ogg", ".mp3", ".m4a", ".mp4"} or not magic_ok:
        raise CaptureMediaError("Use a valid WAV, WebM, OGG, MP3 or M4A recording.")
    model_path = _whisper_model_path()
    if not _has_module("faster_whisper") or not model_path:
        raise CaptureMediaError("Local speech is unavailable: install Faster-Whisper and cache its small model first. Use text entry meanwhile.", "unavailable")
    try:
        with tempfile.TemporaryDirectory(prefix="shelfloop-audio-") as folder:
            source = Path(folder) / ("recording" + suffix)
            source.write_bytes(data)
            audio = _decode_bounded_audio(source)
            segments, info = _speech_model(model_path).transcribe(audio, beam_size=1, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments)
        return _text_result(text, "faster-whisper-local", [f"Detected language: {info.language}; verify names and numbers."])
    except CaptureMediaError:
        raise
    except Exception as exc:
        raise CaptureMediaError("The local speech engine could not read this recording. Use text entry.") from exc
