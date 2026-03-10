; Whisper Typer — Inno Setup installer script
; Builds a standard Windows installer from the PyInstaller bundle.
;
; Compile with: ISCC.exe /DAppVersion=1.0.0 /DSourceDir=dist\WhisperTyper /DOutputDir=output setup.iss
; Or use: python installer/build.py (handles everything automatically)

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef SourceDir
  #define SourceDir "dist\WhisperTyper"
#endif

#ifndef OutputDir
  #define OutputDir "output"
#endif

[Setup]
AppName=Whisper Typer
AppVersion={#AppVersion}
AppVerName=Whisper Typer v{#AppVersion}
AppPublisher=buhhrad
AppPublisherURL=https://github.com/buhhrad/whisper-typer
AppSupportURL=https://github.com/buhhrad/whisper-typer/issues
DefaultDirName={autopf}\WhisperTyper
DefaultGroupName=Whisper Typer
UninstallDisplayIcon={app}\WhisperTyper.exe
UninstallDisplayName=Whisper Typer
OutputDir={#OutputDir}
OutputBaseFilename=WhisperTyperSetup
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=..\icons\whisper-typer.ico
WizardStyle=modern
WizardImageFile=compiler:WizModernImage.bmp
WizardSmallImageFile=compiler:WizModernSmallImage.bmp
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startmenu"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
; Copy the entire PyInstaller bundle
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Desktop shortcut
Name: "{userdesktop}\Whisper Typer"; Filename: "{app}\WhisperTyper.exe"; Tasks: desktopicon; \
  Comment: "Local voice typing — offline speech-to-text"
; Start Menu shortcut
Name: "{group}\Whisper Typer"; Filename: "{app}\WhisperTyper.exe"; Tasks: startmenu; \
  Comment: "Local voice typing — offline speech-to-text"
; Start Menu uninstaller
Name: "{group}\Uninstall Whisper Typer"; Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
; Option to launch after install
Filename: "{app}\WhisperTyper.exe"; Description: "Launch Whisper Typer"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up AppData settings on full uninstall
Type: filesandordirs; Name: "{userappdata}\WhisperTyper"

[Code]
// Show a note about first-launch model download
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    WizardForm.FinishedLabel.Caption :=
      'Whisper Typer has been installed on your computer.' + #13#10 + #13#10 +
      'On first launch, the app will download a speech recognition model (~150 MB - 1.6 GB depending on your settings). ' +
      'This requires an internet connection the first time only — after that, everything runs 100% offline.' + #13#10 + #13#10 +
      'Click Finish to exit Setup.';
  end;
end;
