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

function Sign-File($path) {
    <#
        Signing is optional so a developer build never needs a certificate.
        When the environment is configured, a failure to sign is fatal: an
        unsigned release that looks signed is worse than an honest unsigned one.
        See docs/CODE_SIGNING.md.
    #>
    if (-not $env:FIRE_SIGN_ACCOUNT -or -not $env:FIRE_SIGN_PROFILE) { return $false }
    $tool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if (-not $tool) {
        $found = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kitsin" -Recurse `
                 -Filter signtool.exe -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -match 'x64' } | Select-Object -First 1
        if (-not $found) { Fail 'signing is configured but signtool.exe was not found' }
        $tool = $found.FullName
    } else { $tool = $tool.Source }

    & $tool sign /v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 `
        /dlib "$env:FIRE_SIGN_DLIB" /dmdf "$env:FIRE_SIGN_METADATA" $path
    if ($LASTEXITCODE -ne 0) { Fail "signing failed for $path" }
    return $true
}


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

Step 'sign application'
$signed = Sign-File 'dist\FIRE\FIRE.exe'
if ($signed) { Write-Host 'FIRE.exe signed' -ForegroundColor Green }
else { Write-Host 'not signed (no certificate configured)' -ForegroundColor Yellow }

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
Step 'sign installer'
$signedSetup = Sign-File $setup

$mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host "`n$setup  ($mb MB)" -ForegroundColor Green
if ($signedSetup) {
    Write-Host 'Signed. Both the installer and FIRE.exe inside it.' -ForegroundColor Green
} else {
    Write-Host 'NOT SIGNED. First run will show a SmartScreen warning until a code' -ForegroundColor Yellow
    Write-Host 'signing certificate is in place. See docs/CODE_SIGNING.md.' -ForegroundColor Yellow
}
