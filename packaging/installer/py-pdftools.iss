; py-pdftools, which edits PDF documents: annotates, redacts, labels, stamps,
; arranges and imposes their pages.
; Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
;
; This program is free software: you can redistribute it and/or modify it
; under the terms of the GNU General Public License as published by the
; Free Software Foundation, either version 3 of the License, or (at your
; option) any later version. This program is distributed WITHOUT ANY
; WARRANTY; see the LICENSE.txt file, or <https://www.gnu.org/licenses/>.
;
; El instalador de py-pdftools para Windows, hecho con Inno Setup 6.
; tools/bundle-installer.py arma la carpeta SourceDir (python\, con
; py-pdftools dentro, py-pdftools.ico, LICENSE.txt) y corre ISCC con /D para
; cada valor:
;
;   ISCC /DAppVersion=1.16.0 /DFileVersion=1.16.0.0 /DSourceDir=... \
;        /DOutputDir=... /DOutputName=... py-pdftools.iss
;
; Instala para el usuario (sin permisos de administrador) o para todos,
; según se elija al empezar (o /CURRENTUSER, /ALLUSERS). Silencioso:
; /VERYSILENT /SUPPRESSMSGBOXES [/TASKS="desktopicon"].

#ifndef AppVersion
  #error Give the version: ISCC /DAppVersion=... (tools/bundle-installer.py does)
#endif
#ifndef FileVersion
  #define FileVersion AppVersion + ".0.0"
#endif
#ifndef SourceDir
  #define SourceDir "image"
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputName
  #define OutputName "py-pdftools-" + AppVersion + "-windows-x64-setup"
#endif

#define ProgId "py-pdftools.pdf"

[Setup]
; (no cambiar nunca: así Windows reconoce las versiones como un programa)
AppId={{C2BDCF32-2C91-4BE6-A40D-97138BBCA219}
AppName=py-pdftools
AppVersion={#AppVersion}
AppVerName=py-pdftools {#AppVersion}
AppPublisher=Nicolas Vaughan
AppPublisherURL=https://github.com/nivaca/py-pdftools
AppSupportURL=https://github.com/nivaca/py-pdftools/issues
AppUpdatesURL=https://github.com/nivaca/py-pdftools/releases
AppContact=nicolasvaughan@proton.me
AppCopyright=Copyright (C) 2026 Nicolas Vaughan
AppComments=Edits PDF documents: annotations, redaction, page labels, stamps, imposition. GPL-3.0-or-later.
VersionInfoVersion={#FileVersion}
VersionInfoDescription=py-pdftools setup
; El nombre y la versión del producto, que SignPath comprueba antes de firmar
; (packaging/signpath/artifact-configuration.xml)
VersionInfoProductName=py-pdftools
VersionInfoProductVersion={#FileVersion}
VersionInfoProductTextVersion={#AppVersion}
DefaultDirName={autopf}\py-pdftools
DefaultGroupName=py-pdftools
DisableProgramGroupPage=yes
LicenseFile={#SourceDir}\LICENSE.txt
; Per user by default; the first page offers to install for everyone
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#SourceDir}\py-pdftools.ico
UninstallDisplayIcon={app}\py-pdftools.ico
UninstallDisplayName=py-pdftools {#AppVersion}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.Comment=Edit PDF documents: annotate, redact, label, stamp, arrange and impose their pages
spanish.Comment=Editar documentos PDF: anotar, censurar, etiquetar, sellar, ordenar e imponer sus páginas
english.TaskOpenWith=Offer py-pdftools in "Open with" for PDF documents
spanish.TaskOpenWith=Ofrecer py-pdftools en «Abrir con» para los documentos PDF
english.GroupOther=Other tasks:
spanish.GroupOther=Otras tareas:
english.PdfFile=PDF document
spanish.PdfFile=Documento PDF

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "openwith"; Description: "{cm:TaskOpenWith}"; GroupDescription: "{cm:GroupOther}"

[InstallDelete]
; Lo de la versión anterior, para que no queden archivos que ya no son del
; programa (la configuración del usuario está en otra parte)
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\py-pdftools"; Filename: "{app}\python\pythonw.exe"; Parameters: "-s -m py_pdftools.gui"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\py-pdftools.ico"; Comment: "{cm:Comment}"
Name: "{autodesktop}\py-pdftools"; Filename: "{app}\python\pythonw.exe"; Parameters: "-s -m py_pdftools.gui"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\py-pdftools.ico"; Comment: "{cm:Comment}"; Tasks: desktopicon

[Registry]
; «Abrir con»: un tipo de archivo propio (sin quitarle a nadie su programa
; predeterminado), con el nombre y el ícono de py-pdftools
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "{cm:PdfFile}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\py-pdftools.ico"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "py-pdftools"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\python\pythonw.exe"" -s -m py_pdftools.gui ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-s -m py_pdftools.gui"; WorkingDir: "{%USERPROFILE}"; Description: "{cm:LaunchProgram,py-pdftools}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; (the bytecode Python writes while it runs, if it could)
Type: filesandordirs; Name: "{app}\python"
Type: dirifempty; Name: "{app}"
