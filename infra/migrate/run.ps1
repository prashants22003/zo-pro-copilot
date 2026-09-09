# One-time Wide World Importers .bak → Postgres dump.
# Does not use the GPU. SQL Server RAM is capped at 2 GB inside Docker.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Bak = Join-Path $Root "data\WideWorldImporters-Full.bak"
if (-not (Test-Path $Bak)) {
    Write-Error "Missing $Bak"
}

$Compose = Join-Path $PSScriptRoot "docker-compose.yml"
Write-Host "Starting SQL Server + Postgres (memory-capped, no GPU)…"
docker compose -f $Compose up -d postgres sqlserver

Write-Host "Building migrate image and copying allow-listed tables…"
docker compose -f $Compose build migrate
docker compose -f $Compose run --rm migrate
if ($LASTEXITCODE -ne 0) {
    Write-Error "Migrate failed (exit $LASTEXITCODE). SQL Server logs: docker compose -f `"$Compose`" logs sqlserver"
}

Write-Host "Writing data/wwi-postgres.dump …"
docker compose -f $Compose exec -T postgres pg_dump -Fc -U zopro -d zopro -f /dump/wwi-postgres.dump
if ($LASTEXITCODE -ne 0) {
    Write-Error "pg_dump failed"
}

Write-Host "Stopping SQL Server to free RAM. Postgres stays up on localhost:5433 for inspection."
docker compose -f $Compose stop sqlserver

$Dump = Join-Path $Root "data\wwi-postgres.dump"
$Report = Join-Path $Root "data\migrate-report.txt"
Write-Host "Done."
Write-Host "  Dump:   $Dump"
Write-Host "  Report: $Report"
Write-Host "  Inspect: localhost:5433  user zopro  password zopro_local_dev  db zopro"
Write-Host "When finished inspecting: docker compose -f `"$Compose`" down"
