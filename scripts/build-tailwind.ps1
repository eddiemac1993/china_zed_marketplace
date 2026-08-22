# Builds the compiled Tailwind CSS used by core/templates/core/base.html.
# Run this after changing any Tailwind class usage in templates.
#
# Usage:
#   .\scripts\build-tailwind.ps1            # one-off minified build
#   .\scripts\build-tailwind.ps1 -Watch     # rebuild on save during development

param(
    [switch]$Watch
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cli = Join-Path $root "tools\tailwindcss.exe"
$input = Join-Path $root "core\static_src\tailwind\input.css"
$output = Join-Path $root "core\static\core\css\tailwind.css"

if (-not (Test-Path $cli)) {
    Write-Host "Downloading Tailwind standalone CLI..."
    New-Item -ItemType Directory -Force -Path (Split-Path $cli) | Out-Null
    Invoke-WebRequest -Uri "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-windows-x64.exe" -OutFile $cli
}

New-Item -ItemType Directory -Force -Path (Split-Path $output) | Out-Null

if ($Watch) {
    & $cli -i $input -o $output --watch
} else {
    & $cli -i $input -o $output --minify
    Write-Host "Built $output"
}
