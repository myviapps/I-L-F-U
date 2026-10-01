# Install on Windows

Status: early test version. Windows capture and speech-to-text have not yet been verified on a real call; please report what you see.

## Install

1. On GitHub, open the repository, choose **Code > Download ZIP**, and extract it.
2. Open the extracted folder, then the `windows` folder.
3. Right-click `install.ps1` and choose **Run with PowerShell**. If Windows blocks it, open PowerShell in that folder and run:
   `powershell -ExecutionPolicy Bypass -File .\install.ps1`
4. The script needs Python 3.11 or newer. If it is missing, the script offers to install it with winget.
5. When it finishes, open **I-L-F-U Call Transcriber** from the Start Menu.

No administrator rights are needed. Everything goes into `%LOCALAPPDATA%\ILFU`.

## Use

1. Start your call as usual (Zoom, Teams, Meet or any other app).
2. In the I-L-F-U window, click **Start recording** and confirm the consent reminder. Your own voice and the call's audio are recorded as separate tracks.
3. When the call ends, click **Stop and transcribe**. The first time, the app downloads a speech model sized for your computer (about 150 MB to 1.5 GB).
4. Read the transcript in the window. It is also saved in `Documents\ILFU\sessions\<date-time>\` together with the audio.

Everything runs on your computer. No account, no key, no upload.

## Uninstall

Any one of these:

- **Settings > Apps > Installed apps > I-L-F-U Call Transcriber > Uninstall**
- In the app: **Help > Uninstall...**
- Run `windows\uninstall.ps1` (add `-RemoveData` to also delete your recordings, `-Quiet` for no prompts)

The uninstaller removes the app, downloaded models, the Start Menu shortcut and the Settings entry. It asks whether to keep your recordings and transcripts (kept by default).

## Troubleshooting

- **No sound captured:** make sure the call is playing through your default speakers or headphones, and that microphone access is allowed in Windows Settings > Privacy & security > Microphone.
- **Model download fails:** check your internet connection and run again; downloads resume.
- **Report a problem:** open a GitHub issue and include the OS version and the output of `ilfu tier` from `%LOCALAPPDATA%\ILFU\venv\Scripts\ilfu.exe tier`.
