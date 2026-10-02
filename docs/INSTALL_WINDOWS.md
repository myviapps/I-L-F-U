# Install on Windows

Status: early test version. Setup, install, uninstall, recording with a fake audio source and speech-to-text are tested automatically on Windows. Capturing a real call on a real PC has not been verified yet; please report what you see.

## Install

1. On GitHub, open the repository, choose **Code > Download ZIP**, and extract it.
2. Open the extracted folder, then the `windows` folder.
3. Right-click `install.ps1` and choose **Run with PowerShell**. If Windows blocks it, open PowerShell in that folder and run:
   `powershell -ExecutionPolicy Bypass -File .\install.ps1`
4. The script needs Python 3.11 or newer. If it is missing, the script offers to install it with winget.
5. When it finishes, open **I-L-F-U Call Transcriber** from the Start Menu.

No administrator rights are needed. Everything goes into `%LOCALAPPDATA%\ILFU`.

## First run (setup)

The app opens in its own window (it uses the Microsoft Edge or Google Chrome already on your computer, so there is nothing else to install). The first time, a setup screen walks you through everything before you can record:

1. **Welcome:** read and accept the agreement.
2. **Save location:** pick the folder for recordings and transcripts. Use **Browse** or type a path.
3. **Language and model:** pick the language you mostly hear and a speech model. The one recommended for your computer is marked. For Hindi, Telugu and other regional languages choose Accurate or Best (see `docs/LANGUAGES.md`).
4. **Download:** the model downloads once, with a progress bar. This is the only time the app uses the internet.

You can change the language, model and save folder later in **Settings**.

## Use

1. Start your call as usual (Zoom, Teams, Meet or any other app).
2. In I-L-F-U, click **Start recording** and confirm the reminder. Your own voice and the call's audio are recorded as separate tracks ("You" and "Them").
3. Captions appear while you talk. Use **Pause** and **Resume** to leave out parts of the call.
4. Click **Stop**. The transcript is saved right away, together with the audio.
5. Every recording appears in the list on the left. Select one to read it, play the audio (click a time to jump there), search the text, rename it, delete it, copy it, export it (Markdown, text or subtitles) or **Re-transcribe** it for the most accurate result.

Everything runs on your computer. No account, no key, no upload. If something goes wrong, the file `ilfu.log` in `%LOCALAPPDATA%\ILFU` says what happened; attach it to a bug report.

## Uninstall

Any one of these:

- **Settings > Apps > Installed apps > I-L-F-U Call Transcriber > Uninstall**
- In the app: **Settings > Uninstall**
- Run `windows\uninstall.ps1` (add `-RemoveData` to also delete your recordings, `-Quiet` for no prompts)

The uninstaller removes the app, downloaded models, the Start Menu shortcut and the Settings entry. It asks whether to keep your recordings and transcripts (kept by default).

## Troubleshooting

- **No sound captured:** make sure the call is playing through your default speakers or headphones, and that microphone access is allowed in Windows Settings > Privacy & security > Microphone.
- **Model download fails:** check your internet connection and press **Try again** on the setup screen; downloads resume.
- **Captions lag behind:** your computer is too slow for the chosen model. Pick a smaller one in Settings. The recording itself is never affected, and Re-transcribe gives the full result afterwards.
- **Report a problem:** open a GitHub issue and include the OS version and the output of `ilfu tier` from `%LOCALAPPDATA%\ILFU\venv\Scripts\ilfu.exe tier`.
