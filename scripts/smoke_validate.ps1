param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$SpecPath = "rules/spec.xlsx",
    [string]$InputPath = "samples/input.xml",
    [string]$OutputPath = "samples/output.xml"
)

if (!(Test-Path $SpecPath)) {
    Write-Error "Spec file not found: $SpecPath"
    exit 2
}
if (!(Test-Path $InputPath)) {
    Write-Error "Input XML file not found: $InputPath"
    exit 2
}
if (!(Test-Path $OutputPath)) {
    Write-Error "Output XML file not found: $OutputPath"
    exit 2
}

$uri = "$BaseUrl/validate"

try {
    $response = Invoke-RestMethod -Method Post -Uri $uri -Form @{
        mapping_spec = Get-Item $SpecPath
        input_payload = Get-Item $InputPath
        output_payload = Get-Item $OutputPath
    }
} catch {
    Write-Error "Smoke test request failed: $($_.Exception.Message)"
    exit 1
}

if ($null -eq $response.summary -or $null -eq $response.summary.status) {
    Write-Error "Smoke test failed: response missing summary.status"
    exit 1
}

$status = [string]$response.summary.status
$errorCount = [int]$response.summary.error_count
$reportId = [string]$response.report_id

Write-Output "Smoke test OK"
Write-Output "status=$status"
Write-Output "error_count=$errorCount"
Write-Output "report_id=$reportId"

exit 0
