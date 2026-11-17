# Fish Voiceover for DaVinci Resolve

Generate speech with [fish.audio](https://fish.audio) right from the Resolve timeline: the audio is saved to
`<Output root>\Projects\<project name>\` and inserted at the playhead, with the voiced text as a clip marker.

## Requirements

- Windows, DaVinci Resolve 21 (free or Studio).
- Python 3 from [python.org](https://www.python.org/downloads/windows/) with **tcl/tk** (default installer options).
- fish.audio API key: https://fish.audio/app/api-keys/

## Installation

1. Close DaVinci Resolve (optional; the script also appears without a restart).
2. Open PowerShell in this folder and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1 -ApiKey "sk-fish-..."
   ```

   `-ApiKey` can be omitted; the window then opens **Settings** on first use.
3. In Resolve: **Workspace > Scripts > Fish Voiceover**. The window should open.

The installer:

| What | Where |
|---|---|
| Resolve script | `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Fish Voiceover.lua` |
| Background helper | `%APPDATA%\FishVoiceoverResolve\fish_service.pyw` (started now and on every Windows sign-in via the Startup shortcut `Fish Voiceover for Resolve`) |
| Settings | `%APPDATA%\FishVoiceoverResolve\config.json` |
| Exchange folder | `%USERPROFILE%\Documents\FishVoiceoverResolve\queue` |

To update after code changes, run `install.ps1` again (settings are kept).

### Uninstall

Delete the Resolve script, the `%APPDATA%\FishVoiceoverResolve` and `Documents\FishVoiceoverResolve` folders,
the Startup shortcut (`shell:startup`), and stop `pythonw.exe` running `fish_service.pyw`.

## User guide

### Generate a voiceover

1. Open the project and timeline, put the playhead where the phrase should start.
2. Choose **Workspace > Scripts > Fish Voiceover** (works on any page).
3. In the **Fish Voiceover** window:
   - type or paste the text;
   - **Voice** — pick a voice from the dropdown (Мака, Sarah, …);
   - **Volume (dB)** — loudness change, default `3`;
   - **Speed** — `0.5`–`2.0`, default `1.0`;
   - **Model** — fish.audio model, default `s2.1-pro`.
4. Press **Generate & Insert** or **Ctrl+Enter**. The window closes when the audio is ready.

The last Voice, Volume, Speed and Model are remembered. **Cancel** or **Esc** closes the window without inserting anything.

### What you get

- **File:** `<Output root>\Projects\<project name>\<date_time>_<voice>_<start of text>.wav`
  (default output root `C:\Users\<you>\Videos`).
- **Timeline:** the clip starts exactly at the playhead, on the first unlocked audio track that is empty for the clip's
  length; if all are busy, a new stereo audio track is added.
- **Media Pool:** the clip goes to the **Fish Voiceover** bin.
- **Text:** a blue marker on the clip named `text`; the voiced text is in its **Notes**.
  Hover the marker or double-click it to read the text; all texts are listed in **Index > Markers** on the Edit page.

### Voices and other settings

Click **Settings** in the window:

- **fish.audio API key** — your key from https://fish.audio/app/api-keys/.
- **Output root** — the folder that contains `Projects`.
- **Voices** — one per line as `Name = model ID`. The ID is the last part of the voice URL:
  `https://fish.audio/app/m/933563129e564b19a115bedd57b7406a` → `Sarah = 933563129e564b19a115bedd57b7406a`.

Press **Save**; the new voices appear in the **Voice** dropdown immediately.

### Tips

- Long texts work, but one window = one clip; split long narration into phrases to place them precisely.
- To redo a phrase, delete the clip on the timeline (Undo with **Ctrl+Z** also works) and generate again — old files stay in the project folder.
- Lock an audio track (padlock icon) to keep voiceovers off it.

## How it works

Free Resolve runs Workspace scripts in a Lua sandbox without file I/O, processes, HTTP or UI, so the work is split:

- `Fish Voiceover.lua` writes a `FISHVO_REQ` line to Resolve's log (`printerr`), waits for the answer, imports the WAV,
  places it with `AppendToTimeline` and adds the marker.
- `fish_service.pyw` tails `ResolveDebug.txt`, shows the tkinter window, calls `POST /v1/tts`, saves a stereo WAV and
  answers with tiny marker WAVs in the queue folder whose names carry the percent-encoded path and text
  (read in Lua via `MediaStorage:GetFileList`).

## Troubleshooting

- Nothing opens after choosing the script: the helper isn't running — run `install.ps1` again or start
  `pythonw "%APPDATA%\FishVoiceoverResolve\fish_service.pyw"`.
- Errors from the script appear as a **Fish Voiceover** message box; details are also in
  `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\logs\ResolveDebug.txt` (search `FISHVO`).
