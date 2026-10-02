; Builds ILFU-Setup-<version>.exe: one file that installs the app for the current user.
; It carries the app source and runs windows\install.ps1, which sets up Python, a private
; environment, the Start Menu shortcut and the Settings > Apps entry (so removal also works there).
; Build:  ISCC.exe /DAppVersion=0.0.1 windows\installer\ilfu.iss   (output goes to dist\)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C7E52-3B7A-4C1E-9D55-1F0A5E0C1F11}
AppName=I-L-F-U Call Transcriber
AppVersion={#AppVersion}
AppPublisher=I-L-F-U contributors
AppPublisherURL=https://github.com/myviapps/I-L-F-U
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=ILFU-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
DisableProgramGroupPage=yes
DisableReadyPage=yes

[Files]
Source: "..\..\engine\*"; DestDir: "{tmp}\ilfu-src\engine"; Excludes: "__pycache__,*.pyc,.pytest_cache,.ruff_cache,*.egg-info,tests"; Flags: recursesubdirs createallsubdirs
Source: "..\..\windows\install.ps1"; DestDir: "{tmp}\ilfu-src\windows"
Source: "..\..\windows\uninstall.ps1"; DestDir: "{tmp}\ilfu-src\windows"

[Run]
Filename: "{localappdata}\ILFU\venv\Scripts\pythonw.exe"; Parameters: "-m ilfu.gui"; Description: "Open I-L-F-U now"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Window: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if WizardSilent then Window := SW_HIDE else Window := SW_SHOW;
    WizardForm.StatusLabel.Caption := 'Installing I-L-F-U. This downloads a few hundred MB, please wait...';
    if (not Exec('powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\ilfu-src\windows\install.ps1') +
        '" -Source "' + ExpandConstant('{tmp}\ilfu-src') + '"',
        '', Window, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      SuppressibleMsgBox('The installation did not finish. Check your internet connection and run the setup again. ' +
        'If it keeps failing, open an issue on the project page and include the text shown in the black window.',
        mbError, MB_OK, IDOK);
    end;
  end;
end;
