; Heron AI for AutoCAD - the one-file setup a modeller double-clicks (issue #73, D-99).
;
; Build it with tools/make_installer.py, never by hand: that script passes the versions
; (from autocad/Directory.Build.props and src/autocad_mcp/__init__.py) and the release
; folder tools/make_release.py made. Compiler: Inno Setup 6.7.3 (release.yml pins it).
;
; It puts the same files in the same places as the zip's Install.bat, for the current
; Windows user only (no administrator password):
;   the plug-in -> %APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle
;   the server  -> %LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe
; and then runs Install.ps1 -Connect, the same lines Install.bat uses to tell Claude Code
; and Claude Desktop where the server is. Its uninstaller runs Install.ps1 -Disconnect,
; then removes only the files it installed: saved commands, check lists, logs and the
; audit in %LOCALAPPDATA%\Heron\autocad are the modeller's and stay.
; Setup and its uninstaller both refuse while AutoCAD is open.
; Keep this file plain ASCII.

#ifndef AppVersion
  #error Build this with tools/make_installer.py: it passes AppVersion, ServerVersion, ReleaseDir, OutputDir and SetupName.
#endif

[Setup]
; Fixed for the life of the product, like the bundle's UpgradeCode (tools/build_plugin.py):
; Windows tells an update of Heron from a different program by it.
AppId={{9B2C4D6E-8F10-4A3B-8C5D-7E9F1A2B3C40}
AppName=Heron AI for AutoCAD
AppVersion={#AppVersion}
AppVerName=Heron AI for AutoCAD {#AppVersion}
AppPublisher=Ajmal PS
AppPublisherURL=https://github.com/Ajmalpshaik/Heron-AutoCAD
AppSupportURL=https://github.com/Ajmalpshaik/Heron-AutoCAD/issues
AppUpdatesURL=https://github.com/Ajmalpshaik/Heron-AutoCAD/releases
AppCopyright=Copyright (c) 2026 Ajmal PS
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Heron AI for AutoCAD setup (plug-in {#AppVersion}, server {#ServerVersion})
; This Windows user only: no administrator password, nothing for other users.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Heron\autocad
DisableDirPage=yes
UsePreviousAppDir=no
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
InfoBeforeFile=BEFORE-YOU-INSTALL.txt
OutputDir={#OutputDir}
OutputBaseFilename={#SetupName}
UninstallDisplayName=Heron AI for AutoCAD
UninstallDisplayIcon={app}\autocad-mcp.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
; Setup refuses while AutoCAD or Heron's server runs (below), so it never closes programs itself.
CloseApplications=no
RestartApplications=no
; A log in %TEMP% (Setup Log <date>.txt), for whoever helps when something goes wrong.
SetupLogging=yes
#ifdef SignTool
; Only when tools/make_installer.py was given a certificate (#72): signs Setup and its uninstaller.
SignTool={#SignTool}
SignedUninstaller=yes
#endif

[InstallDelete]
; An update replaces the whole bundle, as Install.bat does, so no file of an older version stays.
Type: filesandordirs; Name: "{userappdata}\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle"

[Files]
Source: "{#ReleaseDir}\HeronAutoCAD.bundle\*"; DestDir: "{userappdata}\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ReleaseDir}\autocad-mcp.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\Install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\CheckForUpdate.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Heron AI for AutoCAD\Check for a newer Heron"; Filename: "{app}\CheckForUpdate.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\Heron AI for AutoCAD\Remove Heron AI for AutoCAD"; Filename: "{uninstallexe}"

[UninstallDelete]
; The earlier version Install.bat keeps for Rollback.bat, when the zip was used before.
Type: filesandordirs; Name: "{app}\previous"

[Code]
var
  ConnectReport: String;

function ServerDir: String;
begin
  Result := ExpandConstant('{localappdata}\Heron\autocad');
end;

function PowerShell: String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

function InstallScript(const Mode: String): String;
begin
  Result := '-NoProfile -ExecutionPolicy Bypass -File "' + ServerDir + '\Install.ps1" ' + Mode;
end;

// tasklist, when Windows' process list (WMI) cannot be read: by name only.
function RunningByName(const ExeName: String): Boolean;
var
  ResultCode, I: Integer;
  Output: TExecOutput;
begin
  Result := False;
  try
    if ExecAndCaptureOutput(ExpandConstant('{sys}\tasklist.exe'), '/FI "IMAGENAME eq ' + ExeName + '" /NH', '',
        SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode, Output) then
      for I := 0 to GetArrayLength(Output.StdOut) - 1 do
        if Pos(LowerCase(ExeName), LowerCase(Output.StdOut[I])) > 0 then
          Result := True;
  except
    Log('Could not run tasklist: ' + GetExceptionMessage);
  end;
end;

// True when ExeName runs. With InFolder, only a copy that runs from that folder counts, so a
// developer's own server somewhere else does not stop Setup.
function IsRunning(const ExeName, InFolder: String): Boolean;
var
  Locator, Service, Found, Item, ExePath: Variant;
  Count, I: Integer;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Found := Service.ExecQuery('SELECT ExecutablePath FROM Win32_Process WHERE Name = ''' + ExeName + '''');
    Count := Found.Count;
    for I := 0 to Count - 1 do
    begin
      if InFolder = '' then
      begin
        Result := True;
        Exit;
      end;
      Item := Found.ItemIndex(I);
      ExePath := Item.ExecutablePath;
      if not VarIsNull(ExePath) then
        if PathSame(ExtractFileDir(ExePath), InFolder) then
        begin
          Result := True;
          Exit;
        end;
    end;
  except
    Log('Could not read the process list, using tasklist: ' + GetExceptionMessage);
    Result := RunningByName(ExeName);
  end;
end;

// What has to be closed first, in plain words, or '' when nothing is in the way.
function InTheWay(const Again, Nothing: String): String;
begin
  Result := '';
  if IsRunning('acad.exe', '') then
    Result := 'AutoCAD is open. Close AutoCAD, then ' + Again + '.' + #13#10#13#10 + Nothing
  else if IsRunning('autocad-mcp.exe', ServerDir) then
    Result := 'Claude is using Heron''s server. Quit Claude Desktop (right-click its icon by the clock, Quit) '
      + 'and close Claude Code, then ' + Again + '.' + #13#10#13#10 + Nothing;
end;

function InitializeSetup(): Boolean;
var
  Why: String;
begin
  Why := InTheWay('run this setup again', 'Nothing was changed.');
  Result := Why = '';
  if not Result then
    SuppressibleMsgBox(Why, mbError, MB_OK, IDOK);
end;

// Checked again just before copying: AutoCAD may have been started while the wizard was open.
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := InTheWay('run this setup again', 'Nothing was changed.');
end;

// After the files are in place: tell Claude Code and Claude Desktop where the server is.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode, I: Integer;
  Output: TExecOutput;
  Line: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  ConnectReport := '';
  try
    if ExecAndCaptureOutput(PowerShell, InstallScript('-Connect'), ServerDir, SW_SHOWNORMAL,
        ewWaitUntilTerminated, ResultCode, Output) then
    begin
      for I := 0 to GetArrayLength(Output.StdOut) - 1 do
      begin
        Line := Trim(Output.StdOut[I]);
        Log('Install.ps1 -Connect: ' + Line);
        if Line <> '' then
          ConnectReport := ConnectReport + Line + #13#10;
      end;
      if ResultCode <> 0 then
        ConnectReport := ConnectReport + 'Claude was not set up (code ' + IntToStr(ResultCode) + '). '
          + 'Close AutoCAD and Claude, then run this setup again.' + #13#10;
    end
    else
      ConnectReport := 'Claude was not set up: Windows PowerShell did not start ('
        + SysErrorMessage(ResultCode) + ').' + #13#10;
  except
    ConnectReport := 'Claude was not set up: ' + GetExceptionMessage + #13#10;
  end;
  Log(ConnectReport);
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Grown: Integer;
begin
  if CurPageID <> wpFinished then
    Exit;
  WizardForm.FinishedLabel.Caption :=
    'Heron AI for AutoCAD {#AppVersion} is installed for your Windows user.' + #13#10#13#10
    + ConnectReport + #13#10
    + 'Start AutoCAD, open the Heron tab and press Heron to connect. Everything starts locked: '
    + 'press Settings and turn Changes on before Claude may draw.' + #13#10#13#10
    + 'To remove it later: Windows Settings > Apps > Heron AI for AutoCAD.';
  Grown := WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
  Log('Finished page text grew by ' + IntToStr(Grown) + ' pixels');
end;

function InitializeUninstall(): Boolean;
var
  Why: String;
begin
  Why := InTheWay('remove Heron again', 'Nothing was removed.');
  Result := Why = '';
  if not Result then
    SuppressibleMsgBox(Why, mbError, MB_OK, IDOK);
end;

// Before the files go: take the "autocad" entry out of Claude Code and Claude Desktop.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  try
    if not ExecAndLogOutput(PowerShell, InstallScript('-Disconnect'), ServerDir, SW_SHOWNORMAL,
        ewWaitUntilTerminated, ResultCode, nil) then
      Log('Could not take Heron out of Claude: ' + SysErrorMessage(ResultCode));
  except
    Log('Could not take Heron out of Claude: ' + GetExceptionMessage);
  end;
end;
