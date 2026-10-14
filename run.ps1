# AEC Management System - Start Script
# This script starts CouchDB, initializes the database, and runs the Django development server

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if (-not $isAdmin) {
    Write-Host "❌ This script must run as Administrator to start CouchDB service." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

Write-Host "🚀 Starting AEC Management System..." -ForegroundColor Cyan
Write-Host ""

# Step 1: Start CouchDB Service
Write-Host "1️⃣  Starting Apache CouchDB service..." -ForegroundColor Yellow
try {
    $couchService = Get-Service "Apache CouchDB" -ErrorAction SilentlyContinue
    if ($couchService) {
        if ($couchService.Status -eq "Running") {
            Write-Host "✅ CouchDB is already running" -ForegroundColor Green
        } else {
            Start-Service "Apache CouchDB"
            Start-Sleep -Seconds 3
            Write-Host "✅ CouchDB started successfully" -ForegroundColor Green
        }
    } else {
        Write-Host "⚠️  Apache CouchDB service not found. Make sure it's installed." -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "❌ Failed to start CouchDB: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Navigate to backend directory
Write-Host "2️⃣  Navigating to backend directory..." -ForegroundColor Yellow
cd backend
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to navigate to backend directory" -ForegroundColor Red
    exit 1
}
Write-Host "✅ In backend directory" -ForegroundColor Green

Write-Host ""

# Step 3: Initialize CouchDB (idempotent)
Write-Host "3️⃣  Initializing CouchDB and Mango indexes..." -ForegroundColor Yellow
& myenv\Scripts\python.exe manage.py init_couchdb
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to initialize CouchDB" -ForegroundColor Red
    exit 1
}
Write-Host "✅ CouchDB initialized" -ForegroundColor Green

Write-Host ""

# Step 4: Run Django development server
Write-Host "4️⃣  Starting Django development server..." -ForegroundColor Yellow
Write-Host ""
Write-Host "🎉 AEC Management System is running!" -ForegroundColor Cyan
Write-Host "📍 Access the application at: http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "📊 CouchDB is available at: http://127.0.0.1:5984/" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

& myenv\Scripts\python.exe manage.py runserver
