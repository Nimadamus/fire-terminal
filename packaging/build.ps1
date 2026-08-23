<#
    Release build for FIRE.

    The order matters. Tests, then bundle, then the release gate, then the
    installer. The gate runs BEFORE anything is wrapped for distribution, so a
    private file or a stray key can never reach a customer inside a setup exe
    that looks finished.

    Any failing step stops the build. A half-built installer is worse than none.

        powershell -ExecutionPolicy Bypass -File packaging\build.ps1
        powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipTests
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nFAILED: $text" -ForegroundColor Red; exit 1 }

$version = (Select-String -Path 'src\fire\version.py' -Pattern '^VERSION\s*=\s*"(.+)"'
           ).Matches[0].Groups[1].Value
if (-not $version) { Fail 'could not read VERSION from src\fire\version.py' }
Write-Host "FIRE $version" -ForegroundColor Green

if (-not $SkipTests) {
    Step 'tests'
    & python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { Fail 'tests' }
}

Step 'bundle'
Remove-Item -Recurse -Force 'build', 'dist\FIRE' -ErrorAction SilentlyContinue
& pyinstaller 'packaging\fire.spec' --noconfirm --log-level WARN
if ($LASTEXITCODE -ne 0) { Fail 'pyinstaller' }

Step 'release gate'
& python 'packaging\verify_bundle.py' 'dist\FIRE'
if ($LASTEXITCODE -ne 0) { Fail 'release gate: the bundle is not fit to ship' }

if ($SkipInstaller) { Write-Host "`nBundle only. dist\FIRE" -ForegroundColor Green; exit 0 }

Step 'installer'
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Fail 'Inno Setup not found. winget install --id JRSoftware.InnoSetup -e --scope user'
}
& $iscc "/DAppVersion=$version" 'packaging\fire.iss' | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'installer' }

$setup = "dist\installer\FIRE-$version-setup.exe"
if (-not (Test-Path $setup)) { Fail "installer produced no file at $setup" }
$mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)

Write-Host "`n$setup  ($mb MB)" -ForegroundColor Green
Write-Host "NOT SIGNED. First run will show a SmartScreen warning until a code" -ForegroundColor Yellow
Write-Host "signing certificate is in place (LAUNCH_CHECKLIST.md item H5)." -ForegroundColor Yellow
