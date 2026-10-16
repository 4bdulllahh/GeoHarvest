; GeoHarvest installer. Built by tools/build.py, which passes the version and folders:
;   ISCC /DAppVersion=0.1.1 /DTag=v0.1.1-beta /DSourceDir=...\dist\GeoHarvest /DOutputDir=...\build ...
; Installs for the current user only (no admin prompt), so the app can update itself.
; Searches, leads and settings live in %APPDATA%\GeoHarvest, never in the app folder.

#define AppName "GeoHarvest"
#define AppExe "GeoHarvest.exe"

[Setup]
AppId={{6F2B8C1E-4D7A-4E59-9B3C-2A1F0E8D7C64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#Tag}
AppPublisher={#AppName}
AppPublisherURL=https://github.com/4bdulllahh/GeoHarvest
AppSupportURL=https://github.com/4bdulllahh/GeoHarvest/issues
AppUpdatesURL=https://github.com/4bdulllahh/GeoHarvest/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=GeoHarvest-Setup-{#Tag}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Open GeoHarvest when Windows &starts"; GroupDescription: "Start-up:"; Flags: unchecked

[Files]
; Replaces the old program files; the old _internal folder is cleared first so no stale DLLs stay
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open GeoHarvest now"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Asked in /SILENT too (the app's Uninstall button uses it); /SUPPRESSMSGBOXES keeps the data
  if CurUninstallStep = usPostUninstall then
    if SuppressibleMsgBox('Also delete your searches, leads, exported files, settings and saved AI key?' + #13#10 + #13#10 +
              'Choose No to keep them, so they are still there if you install GeoHarvest again.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{userappdata}\GeoHarvest'), True, True, True);
end;
