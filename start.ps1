$ErrorActionPreference = "Continue"
Set-Location "C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness"

# Load full user+machine PATH so child processes can find 'harness'
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "Machine")

& ".venv\Scripts\python.exe" "server.py" 2>&1 | Tee-Object -FilePath "C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness\server_full.log"
