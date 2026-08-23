; Windows installer for FIRE.
;
; Deliberate choices, because each one is a support ticket avoided:
;
;   * Per user install, no administrator prompt. A trader installing on a work
;     laptop should not have to argue with IT to try the product.
;   * A fixed AppId, so a new version upgrades in place instead of stacking up
;     second and third copies in Add or Remove Programs.
;   * Uninstall asks before touching customer data, and says plainly that
;     removing the saved key here does NOT revoke it at the exchange. Somebody
;     uninstalling in a hurry because they think they were compromised must not
;     walk away believing they are safe when they are not.
;
; Not signed yet. Until a certificate is in place SmartScreen will warn on
; first run; see LAUNCH_CHECKLIST.md item H5.
;
; Build:  ISCC.exe /DAppVersion=1.0.0 packaging\fire.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "FIRE"
#define AppExe "FIRE.exe"

[Setup]
AppId={{8C0F2A16-9F1B-4D5E-9C3A-6B7E4F2D1A90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=FIRE
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=FIRE-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\docs\LICENSE.txt
SetupIconFile=fire.ico
SetupLogging=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\FIRE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open FIRE"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Customer data lives outside the install directory on purpose, so uninstall
// has to reach for it deliberately. Ask, default to keeping, and never imply
// that deleting a local copy of a key is the same as revoking it.
procedure CurUninstallStepChanged(CurStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\FIRE');
    if DirExists(DataDir) then
    begin
      // SuppressibleMsgBox, not MsgBox. A plain MsgBox here ignores
      // /SUPPRESSMSGBOXES and a silent uninstall hangs forever waiting on a
      // dialog nobody can see, which is exactly how an IT deployment or an
      // upgrade script wedges.
      if SuppressibleMsgBox('Also remove your FIRE settings and the encrypted copy of your'
        + ' API key from this computer?' + #13#10 + #13#10
        + 'This does NOT revoke the key at your exchange. If you think the key'
        + ' has been exposed, revoke it in your exchange account as well.'
        + #13#10 + #13#10
        + 'Choose No to keep your settings for a future reinstall.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
