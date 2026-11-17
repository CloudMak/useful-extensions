# Installs Fish Voiceover into DaVinci Resolve (Workspace > Scripts > Fish Voiceover)
# and the background helper that autostarts with Windows.
param([string]$ApiKey = "")
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$app = Join-Path $env:APPDATA "FishVoiceoverResolve"
$scripts = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts"
New-Item -ItemType Directory -Force $app | Out-Null
# Resolve's MediaStorage can't list AppData, so the exchange folder lives under Documents.
New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE "Documents\FishVoiceoverResolve\queue") | Out-Null
Copy-Item (Join-Path $src "fish_service.pyw") $app -Force
$util = Join-Path $scripts "Utility"
New-Item -ItemType Directory -Force $util | Out-Null
Copy-Item (Join-Path $src "Fish Voiceover.lua") $util -Force

$pyw = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\pythonw.exe") -ErrorAction SilentlyContinue |
       Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $pyw) { $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }
if (-not $pyw) { throw "pythonw.exe not found - install Python 3 from python.org" }

$cfgPath = Join-Path $app "config.json"
$cfg = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { [pscustomobject]@{} }
if ($ApiKey) { $cfg | Add-Member -Force api_key $ApiKey }
[IO.File]::WriteAllText($cfgPath, ($cfg | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding $false))

$service = Join-Path $app "fish_service.pyw"
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "Fish Voiceover for Resolve.lnk"
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = $pyw
$sh.Arguments = "`"$service`""
$sh.WorkingDirectory = $app
$sh.Save()

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like "*fish_service.pyw*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process $pyw -ArgumentList "`"$service`"" -WorkingDirectory $app
"Installed. Helper: $pyw $service"
