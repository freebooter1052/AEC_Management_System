# AEC Management System - start everything with one command (run from an Administrator PowerShell):
#   .\run.ps1
# Starts CouchDB, initialises the database, builds the React frontend and runs the Django server.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root "backend\myenv\Scripts\python.exe"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) { Fail "Run PowerShell as Administrator (needed to start the CouchDB service)." }
if (-not (Test-Path $python)) { Fail "Python venv not found at backend\myenv. See README > Getting Started." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js (npm) not found. Install Node.js 18+ from https://nodejs.org/." }

Step "1/4 Starting Apache CouchDB"
$couch = Get-Service "Apache CouchDB" -ErrorAction SilentlyContinue
if (-not $couch) { Fail "The 'Apache CouchDB' Windows service is not installed." }
if ($couch.Status -ne "Running") { Start-Service "Apache CouchDB"; Start-Sleep -Seconds 3 }
Write-Host "CouchDB is running." -ForegroundColor Green

Step "2/4 Initialising CouchDB and Mango indexes"
Push-Location (Join-Path $root "backend")
try { & $python manage.py init_couchdb; if ($LASTEXITCODE -ne 0) { Fail "init_couchdb failed." } } finally { Pop-Location }

Step "3/4 Building the React frontend"
Push-Location (Join-Path $root "frontend")
try {
    if (-not (Test-Path "node_modules")) { npm install; if ($LASTEXITCODE -ne 0) { Fail "npm install failed." } }
    npm run build; if ($LASTEXITCODE -ne 0) { Fail "Frontend build failed." }
} finally { Pop-Location }

Step "4/4 Starting the Django server"
Write-Host "App:     http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "CouchDB: http://127.0.0.1:5984/_utils/" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
Push-Location (Join-Path $root "backend")
try { & $python manage.py runserver } finally { Pop-Location }
