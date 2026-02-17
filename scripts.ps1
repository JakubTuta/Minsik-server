# ============================================================================
# Minsik Development Automation Scripts
# ============================================================================
# PowerShell script for common development tasks:
# - Compile Protocol Buffer files
# - Create admin accounts
# - Deploy services (dev/prod)
# - Run tests
# ============================================================================

param(
    [switch]$Help,
    [switch]$CompileProto,
    [switch]$CreateAdmin,
    [string]$Email,
    [string]$Password,
    [switch]$Deploy,
    [string]$Environment = "dev",
    [switch]$Test,
    [string]$TestService,
    [switch]$Logs,
    [string]$LogService,
    [switch]$Clean
)

# Ensure we use the venv Python if available
if (Test-Path "venv/Scripts/python.exe") {
    $venvPythonPath = (Resolve-Path "venv/Scripts/python.exe").Path
    $env:PYTHON = $venvPythonPath
    $env:CLOUDSDK_PYTHON = $venvPythonPath
    $venvScriptsPath = (Resolve-Path "venv/Scripts").Path
    if ($env:PATH -notlike "*$venvScriptsPath*") {
        $env:PATH = $venvScriptsPath + ";" + $env:PATH
    }
    $env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'WindowsApps' }) -join ';'
}

# Colors for output
$ColorSuccess = "Green"
$ColorError = "Red"
$ColorInfo = "Cyan"
$ColorWarning = "Yellow"

# ============================================================================
# Helper Functions
# ============================================================================

function Show-Help {
    Write-Host @"
Minsik Development Scripts

Usage: .\scripts.ps1 -<Command> [options]

COMMANDS:

  Protocol Buffers:
    -CompileProto                  Compile all .proto files to Python

  User Management:
    -CreateAdmin                   Create an admin user
      -Email <email>                 Admin email address
      -Password <password>           Admin password

  Deployment:
    -Deploy                        Start dev environment (docker-compose up)
      -Environment prod              Build and push images to GAR (production)

    -Logs                          View service logs
      -LogService <service>          Specific service name

    -Clean                         Stop and remove all containers and volumes

  Testing:
    -Test                          Run tests
      -TestService <service>         Specific service (gateway/ingestion/books/auth/user-data)

  Help:
    -Help                          Show this help message

EXAMPLES:

  .\scripts.ps1 -CompileProto
  .\scripts.ps1 -CreateAdmin -Email admin@minsik.com -Password securepass123
  .\scripts.ps1 -Deploy
  .\scripts.ps1 -Deploy -Environment prod
  .\scripts.ps1 -Logs -LogService books-service
  .\scripts.ps1 -Test -TestService books
  .\scripts.ps1 -Clean

"@ -ForegroundColor $ColorInfo
}

function Write-Step {
    param([string]$Message)
    Write-Host "`n $Message" -ForegroundColor $ColorInfo
}

function Write-Success {
    param([string]$Message)
    Write-Host "$Message" -ForegroundColor $ColorSuccess
}

function Write-Error-Message {
    param([string]$Message)
    Write-Host "$Message" -ForegroundColor $ColorError
}

function Write-Warning-Message {
    param([string]$Message)
    Write-Host "$Message" -ForegroundColor $ColorWarning
}

# ============================================================================
# Command Implementations
# ============================================================================

function Compile-Proto {
    Write-Step "Compiling Protocol Buffer files..."

    if (-not (Test-Path "proto")) {
        Write-Error-Message "proto/ directory not found"
        return
    }

    $protoDefinitions = @(
        @{
            Source = "proto/ingestion.proto"
            Destinations = @("services/ingestion/app/proto", "services/gateway/app/proto")
        },
        @{
            Source = "proto/books.proto"
            Destinations = @("services/books/app/proto", "services/gateway/app/proto")
        },
        @{
            Source = "proto/auth.proto"
            Destinations = @("services/auth/app/proto", "services/gateway/app/proto")
        }
    )

    $totalFiles = $protoDefinitions.Count
    $compiled = 0
    $failed = 0

    Write-Host "  Found $totalFiles proto file(s) to compile" -ForegroundColor $ColorInfo

    foreach ($protoDef in $protoDefinitions) {
        $protoFile = $protoDef.Source
        $protoName = Split-Path $protoFile -Leaf

        if (-not (Test-Path $protoFile)) {
            Write-Warning-Message "Proto file not found: $protoFile"
            $failed++
            continue
        }

        Write-Host "  Compiling $protoName..." -ForegroundColor Gray

        foreach ($destination in $protoDef.Destinations) {
            if (-not (Test-Path $destination)) {
                New-Item -ItemType Directory -Force -Path $destination | Out-Null
            }

            $initFile = Join-Path $destination "__init__.py"
            if (-not (Test-Path $initFile)) {
                New-Item -ItemType File -Path $initFile -Force | Out-Null
            }

            $protoBaseName = [System.IO.Path]::GetFileNameWithoutExtension($protoFile)

            & "$env:PYTHON" -m grpc_tools.protoc `
                -I./proto `
                --python_out=. `
                --grpc_python_out=. `
                --pyi_out=. `
                $protoFile

            if ($LASTEXITCODE -ne 0) {
                Write-Error-Message "Failed to compile $protoName"
                $failed++
                break
            }

            Move-Item -Path "${protoBaseName}_pb2.py" -Destination $destination -Force
            Move-Item -Path "${protoBaseName}_pb2_grpc.py" -Destination $destination -Force
            Move-Item -Path "${protoBaseName}_pb2.pyi" -Destination $destination -Force

            $grpcFile = Join-Path $destination "${protoBaseName}_pb2_grpc.py"
            $content = Get-Content $grpcFile -Raw
            $content = $content -replace "^import ${protoBaseName}_pb2", "from . import ${protoBaseName}_pb2"
            Set-Content -Path $grpcFile -Value $content -NoNewline

            Write-Host "    Compiled to $destination" -ForegroundColor Gray
        }

        if ($LASTEXITCODE -eq 0) {
            $compiled++
        }
    }

    Write-Host ""
    if ($failed -eq 0) {
        Write-Success "Proto compilation complete! ($compiled/$totalFiles files)"
    } else {
        Write-Warning-Message "Proto compilation finished with errors: $compiled succeeded, $failed failed"
    }
}

function Create-Admin-User {
    param(
        [string]$Email,
        [string]$Password
    )

    if (-not $Email -or -not $Password) {
        Write-Error-Message "Email and Password are required"
        Write-Host "Usage: .\scripts.ps1 -CreateAdmin -Email admin@minsik.com -Password securepass" -ForegroundColor $ColorWarning
        return
    }

    Write-Step "Creating admin user: $Email"

    if (-not (Test-Path "scripts/create_admin.py")) {
        Write-Error-Message "scripts/create_admin.py not found"
        return
    }

    $authContainer = & docker ps -q -f name=minsik-auth-service-dev
    if (-not $authContainer) {
        Write-Error-Message "Auth service container (minsik-auth-service-dev) is not running"
        return
    }

    & docker cp scripts/create_admin.py ${authContainer}:/tmp/create_admin.py 2>$null
    & docker exec $authContainer python /tmp/create_admin.py --email $Email --password $Password

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Admin user created successfully!"
    } else {
        Write-Error-Message "Failed to create admin user"
    }
}

function Build-And-Push-Images {
    $GAR_REGISTRY = "europe-central2-docker.pkg.dev/minsik-486117/server"

    $services = @(
        @{ Name = "Auth Service";      Dockerfile = "services/auth/Dockerfile";       ImageName = "auth-service" },
        @{ Name = "Gateway Service";   Dockerfile = "services/gateway/Dockerfile";    ImageName = "gateway-service" },
        @{ Name = "Ingestion Service"; Dockerfile = "services/ingestion/Dockerfile";  ImageName = "ingestion-service" },
        @{ Name = "Books Service";     Dockerfile = "services/books/Dockerfile";      ImageName = "books-service" },
        @{ Name = "User Data Service"; Dockerfile = "services/user_data/Dockerfile";  ImageName = "user-data-service" }
    )

    Write-Step "Building and pushing images to Google Artifact Registry..."

    Write-Host "  Configuring Docker authentication..." -ForegroundColor Gray
    & gcloud auth configure-docker europe-central2-docker.pkg.dev --quiet

    if ($LASTEXITCODE -ne 0) {
        Write-Error-Message "Failed to configure Docker authentication. Run 'gcloud auth login' first."
        return $false
    }

    foreach ($service in $services) {
        $imageTag = "$GAR_REGISTRY/$($service.ImageName):latest"

        Write-Host "  Building $($service.Name)..." -ForegroundColor Gray

        if (-not (Test-Path $service.Dockerfile)) {
            Write-Error-Message "Dockerfile not found at $($service.Dockerfile)"
            return $false
        }

        $absoluteDockerfilePath = (Resolve-Path $service.Dockerfile).Path
        & docker build -t $imageTag -f $absoluteDockerfilePath .

        if ($LASTEXITCODE -ne 0) {
            Write-Error-Message "Failed to build $($service.Name)"
            return $false
        }

        Write-Host "  Pushing $($service.Name)..." -ForegroundColor Gray
        & docker push $imageTag

        if ($LASTEXITCODE -ne 0) {
            Write-Error-Message "Failed to push $($service.Name)"
            return $false
        }

        Write-Host "    $imageTag" -ForegroundColor Green
    }

    Write-Success "All images built and pushed successfully!"
    return $true
}

function Deploy-Services {
    param(
        [string]$Environment = "dev"
    )

    if ($Environment -eq "dev") {
        Write-Step "Starting development environment..."

        if (-not (Test-Path ".env")) {
            Write-Warning-Message ".env file not found, copying from .env.example..."
            Copy-Item ".env.example" ".env"
        }

        & docker-compose up -d --build

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Development environment started!"
            & docker-compose ps
        } else {
            Write-Error-Message "Failed to start development environment"
        }

    } elseif ($Environment -eq "prod") {
        Build-And-Push-Images

    } else {
        Write-Error-Message "Invalid environment: $Environment (use 'dev' or 'prod')"
    }
}

function Show-Logs {
    param(
        [string]$Service
    )

    Write-Step "Viewing logs..."

    if ($Service) {
        & docker-compose logs -f $Service
    } else {
        & docker-compose logs -f
    }
}

function Run-Tests {
    param(
        [string]$Service
    )

    Write-Step "Running tests..."

    $serviceMap = @{
        "gateway"   = "gateway-service"
        "ingestion" = "ingestion-service"
        "books"     = "books-service"
        "auth"      = "auth-service"
        "user-data" = "user-data-service"
    }

    if ($Service -and $Service -ne "all") {
        $containerName = "minsik-$($serviceMap[$Service])-dev"

        $containerCheck = & docker ps -q -f name=$containerName
        if (-not $containerCheck) {
            Write-Error-Message "Container $containerName is not running"
            return
        }

        & docker exec $containerName pytest tests/ -v

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Tests passed!"
        } else {
            Write-Error-Message "Tests failed"
        }

    } else {
        $services = @("gateway", "ingestion", "books", "auth", "user-data")
        $totalPassed = 0
        $totalFailed = 0

        foreach ($svc in $services) {
            Write-Host "`n  Testing $svc..." -ForegroundColor $ColorInfo
            $containerName = "minsik-$($serviceMap[$svc])-dev"

            $containerCheck = & docker ps -q -f name=$containerName
            if (-not $containerCheck) {
                Write-Warning-Message "  Container not running, skipping"
                continue
            }

            & docker exec $containerName pytest tests/ -v

            if ($LASTEXITCODE -eq 0) {
                $totalPassed++
                Write-Success "  $svc passed"
            } else {
                $totalFailed++
                Write-Error-Message "  $svc failed"
            }
        }

        Write-Host "`nTest Summary: $totalPassed passed, $totalFailed failed" -ForegroundColor $ColorInfo
    }
}

function Clean-All {
    Write-Warning-Message "This will stop and remove all containers and volumes!"
    $confirmation = Read-Host "Are you sure? (yes/no)"

    if ($confirmation -ne "yes") {
        Write-Host "Cancelled" -ForegroundColor Gray
        return
    }

    & docker-compose down -v
    & docker volume prune -f

    Write-Success "Cleanup complete!"
}

# ============================================================================
# Main Execution
# ============================================================================

if ($PSBoundParameters.Count -eq 0) {
    Show-Help
    exit
}

if ($Help)         { Show-Help }
if ($CompileProto) { Compile-Proto }
if ($CreateAdmin)  { Create-Admin-User -Email $Email -Password $Password }
if ($Deploy)       { Deploy-Services -Environment $Environment }
if ($Logs)         { Show-Logs -Service $LogService }
if ($Test)         { Run-Tests -Service $TestService }
if ($Clean)        { Clean-All }
