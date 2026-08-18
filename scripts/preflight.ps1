[CmdletBinding()]
param(
    [Parameter()]
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$workRoot = Join-Path $temporaryRoot ("annotateit-preflight-" + [System.Guid]::NewGuid().ToString("N"))
$workRoot = [System.IO.Path]::GetFullPath($workRoot)
$devEnvironment = Join-Path $workRoot "dev"
$smokeEnvironment = Join-Path $workRoot "smoke"
$artifacts = Join-Path $workRoot "dist"
$locationPushed = $false

New-Item -ItemType Directory -Path $workRoot | Out-Null

try {
    Push-Location -LiteralPath $repositoryRoot
    $locationPushed = $true

    Write-Host "Creating isolated development environment with $Python"
    Invoke-Checked -FilePath $Python -Arguments @("-m", "venv", $devEnvironment)
    $devPython = Join-Path $devEnvironment "Scripts\python.exe"

    Invoke-Checked -FilePath $devPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked -FilePath $devPython -Arguments @("-m", "pip", "install", "-e", ".[dev]")

    Invoke-Checked -FilePath $devPython -Arguments @("-m", "ruff", "format", "--check", "src", "tests")
    Invoke-Checked -FilePath $devPython -Arguments @("-m", "ruff", "check", "src", "tests")
    Invoke-Checked -FilePath $devPython -Arguments @("-m", "mypy")
    Invoke-Checked -FilePath $devPython -Arguments @("-m", "pytest", "--cov=annotateit_ai", "--cov-report=term-missing")

    Invoke-Checked -FilePath $devPython -Arguments @("-m", "build", "--outdir", $artifacts)
    $distributionFiles = @(Get-ChildItem -LiteralPath $artifacts -File)
    if ($distributionFiles.Count -ne 2) {
        throw "Expected one source distribution and one wheel, found $($distributionFiles.Count) files."
    }
    Invoke-Checked -FilePath $devPython -Arguments (@("-m", "twine", "check") + @($distributionFiles.FullName))

    $wheels = @($distributionFiles | Where-Object Extension -eq ".whl")
    if ($wheels.Count -ne 1) {
        throw "Expected exactly one wheel, found $($wheels.Count)."
    }

    Invoke-Checked -FilePath $devPython -Arguments @("-m", "venv", $smokeEnvironment)
    $smokePython = Join-Path $smokeEnvironment "Scripts\python.exe"
    $smokeCommand = Join-Path $smokeEnvironment "Scripts\annotateit.exe"
    Invoke-Checked -FilePath $smokePython -Arguments @("-m", "pip", "install", $wheels[0].FullName)
    Invoke-Checked -FilePath $smokeCommand -Arguments @("--help")

    Write-Host "Preflight passed: format, lint, types, tests, distributions, and wheel smoke test."
}
finally {
    if ($locationPushed) {
        Pop-Location
    }

    $safePrefix = $temporaryRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $safeLeaf = Split-Path -Leaf $workRoot
    if (
        $workRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        $safeLeaf -like "annotateit-preflight-*" -and
        (Test-Path -LiteralPath $workRoot)
    ) {
        Remove-Item -LiteralPath $workRoot -Recurse -Force
    }
}
