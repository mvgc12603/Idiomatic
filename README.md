# Idiomatic
Multi-lingual, context-aware idiom matching, wherever you type.


A local-first Chrome extension that helps writers replace rough, literal, or cross-language idioms with culturally natural equivalents.

The extension watches editable text fields as you type. When it sees a bracketed phrase, known idiom, or rough idiom cue, it sends the phrase and surrounding sentence to a local FastAPI backend. The backend first checks a coded multilingual idiom dictionary, then can fall back to an AI + web search  when the idiom is not in the database.

Example:
<img width="1228" height="635" alt="Screenshot 2026-07-18 142738" src="https://github.com/user-attachments/assets/6ffd189b-c9b5-4939-8917-238fea951e40" />


Suggested Spanish idiom:

```text
sobre gustos no hay nada escrito
```

## Features

- Detects idioms and rough phrases while typing in Chrome text fields.
- Supports cross-language idiom lookup across English, Spanish, and French.
- Uses the surrounding sentence to infer the target language.
- Prioritizes a coded idiom database before AI fallback.
- Uses local Ollama by default, so no paid API plan is required.
- Suppresses literal fallback suggestions when they look invented or word-by-word.
- Works on regular websites and local plain-text files.

## Upcoming Features
- Expand functionality to additional languages
- Improve accuracy with incomplete or inaccurate idioms
- Migrate static python 'idiom database' externally
- Connect 'idiom database' to open source sit
- Allow user to chose which AI or web search backup is used

## Project Structure

```text
idiom-tool/
  backend/
    idiom_database.py   # Coded multilingual idiom dictionary and matcher
    main.py             # FastAPI app, fallback providers, debug endpoints
    requirements.txt    # Python backend dependencies
    start_backend.ps1   # Windows helper script for running the API
  extension/
    manifest.json       # Chrome extension manifest
    content.js          # In-page idiom detection and suggestion widget
    popup.html          # Extension popup/status page
```

## Technologies

- Chrome Extension Manifest V3
- JavaScript content script
- Python
- FastAPI
- Pydantic
- Uvicorn
- httpx
- Ollama
- Optional OpenAI fallback
- Optional DeepL fallback
- DuckDuckGo HTML search for lightweight web evidence

## How It Works

1. The Chrome extension detects a candidate phrase while the user types.
2. It sends the phrase, surrounding sentence, target language setting, and tone hint to `http://localhost:8000/suggest-idiom`.
3. The backend checks `IDIOM_DATABASE` first.
4. If the dictionary has a match, it returns suggestions.
5. If the dictionary misses, the backend can ask Ollama to find a real idiom equivalent.
6. Fallback suggestions are filtered to avoid literal translations and low-confidence results.

Important behavior:

- If the surrounding sentence is Spanish, the suggestion should be Spanish even if the bracketed idiom is French or English.
- The bracketed phrase/expression hints at the sentence structure of the returned suggestion.
- The app should prefer no suggestion over a fake or literal idiom.

## Running Locally

### Prerequisites

Install:

- Python 3.12 or newer
- Google Chrome or Chromium
- Ollama, if using the default local fallback

Pull the default Ollama model:

```powershell
ollama pull qwen3:4b
```

### Backend

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Or use the helper script:

```powershell
cd backend
.\start_backend.ps1
```

Health check:

```text
http://localhost:8000/health
```

Test page:

```text
http://localhost:8000/test
```

### Chrome Extension

1. Open Chrome.
2. Go to:

```text
chrome://extensions
```

3. Turn on **Developer mode**.
4. Click **Load unpacked**.
5. Select:

```text
idiom-tool/extension
```

6. Keep the backend running at `http://localhost:8000`.
7. Type a bracketed idiom in a text field, for example:

```text
No me gusta, pero [les gouts et les couleurs ne se discutent pas]
```

## Configuration

The backend reads configuration from environment variables. You can set these in PowerShell before starting the server, or place them in a `.env` file inside `backend/`.

| Variable | Default | Description |
| --- | --- | --- |
| `IDIOM_FALLBACK_PROVIDER` | `ollama` | Fallback after dictionary miss. Options: `none`, `dictionary`, `ollama`, `local`, `openai`, `deepl`, `auto`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server URL. |
| `OLLAMA_MODEL` | `qwen3:4b` | Ollama model used for idiom lookup. |
| `ENABLE_WEB_RETRIEVAL` | `true` | Enables lightweight web evidence lookup. |
| `REQUIRE_WEB_EVIDENCE_FOR_AI_FALLBACK` | `false` | If true, skips AI fallback when no web evidence is found. |
| `ENABLE_UNVERIFIED_AI_FALLBACK` | `false` | If true, returns AI fallback suggestions without strict filtering. |
| `OPENAI_API_KEY` | unset | Required only if using OpenAI fallback. |
| `OPENAI_MODEL` | `gpt-5.6` | OpenAI model name if OpenAI fallback is enabled. |
| `DEEPL_API_KEY` | unset | Required only if using DeepL fallback. |

Recommended free/local setup:

```powershell
$env:IDIOM_FALLBACK_PROVIDER = "ollama"
$env:OLLAMA_MODEL = "qwen3:4b"
```

Dictionary-only mode:

```powershell
$env:IDIOM_FALLBACK_PROVIDER = "dictionary"
```

## Debug Endpoints

Search evidence preview:

```text
http://127.0.0.1:8000/debug/search?phrase=llover%20a%20cantaros&context=I%20went%20outside%20but%20[llover%20a%20cantaros]
```

Dictionary match preview:

```text
http://127.0.0.1:8000/debug/database?phrase=les%20gouts%20et%20les%20couleurs%20ne%20se%20discutent%20pas&context=No%20me%20gusta,%20pero%20[les%20gouts%20et%20les%20couleurs%20ne%20se%20discutent%20pas]
```

## Development Checks

Run Python syntax checks:

```powershell
cd backend
@'
from pathlib import Path
for path in [Path("main.py"), Path("idiom_database.py")]:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
    print(f"ok {path}")
'@ | .\.venv\Scripts\python.exe -
```

Run JavaScript syntax check:

```powershell
cd extension
node --check content.js
```

## Packaging for GitHub Releases

The extension can be shared as a ZIP file for portfolio visitors or testers.

From the project root:

```powershell
Compress-Archive -Path .\extension\* -DestinationPath .\idiom-extension.zip -Force
```

Upload `idiom-extension.zip` to a GitHub Release. Users can download it, unzip it, and load the unpacked extension in Chrome.

Note: GitHub Pages cannot run the local FastAPI/Ollama backend. For a portfolio page, link to the source repo and release ZIP, and include screenshots or a short demo video.

## Portfolio Integration

A good portfolio entry should include:

- Project name: **Contextual Idiom Translator**
- One-line summary: Local-first Chrome extension for culturally natural idiom translation.
- Screenshot or demo GIF of the suggestion widget.
- Link to the GitHub repository.
- Link to the latest GitHub Release ZIP.
- Short architecture note:

```text
Chrome Extension -> Local FastAPI Backend -> Coded Idiom Database -> Ollama/Web Evidence Fallback
```

Suggested portfolio description:

```text
Built a Chrome extension that detects rough or foreign idioms while writing and suggests culturally equivalent idioms in the surrounding sentence's language. The backend uses a coded multilingual idiom database first, then local Ollama fallback with guardrails against literal translation.
```

## Troubleshooting

### Backend Port Error

If Uvicorn reports a socket permission error or port conflict on `8000`, run the backend on another port:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8010
```

Then update `API_URL` in `extension/content.js` to match the new port.

### Ollama Is Not Connected

Make sure Ollama is running:

```powershell
ollama list
```

Pull the configured model:

```powershell
ollama pull qwen3:4b
```

### Extension Shows No Suggestions

Check:

- The backend is running.
- Chrome loaded the `extension/` folder, not the project root.
- The phrase is bracketed, such as `[meter la pata]`.
- The backend health page works at `http://127.0.0.1:8000/health`.
- The idiom may not exist in the coded database, and Ollama may have rejected it rather than inventing a literal answer.

## Limitations

- The backend runs locally; it is not hosted by GitHub Pages.
- Ollama fallback quality depends on the installed local model.
- The dictionary is intentionally curated and incomplete.
- Some web evidence may be unavailable depending on network restrictions.
- For public one-click installation, the extension should eventually be published through the Chrome Web Store.

## License

No license has been added yet. Add a license before publishing the repository publicly if you want others to reuse or contribute to the project.

