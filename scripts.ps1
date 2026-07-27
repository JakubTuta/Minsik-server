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
    [switch]$Migrate,
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
      -Environment prod              Build and push images to container registry (production)

    -Migrate                       Run database migrations manually (docker run --rm db-migrator)

    -Logs                          View service logs
      -LogService <service>          Specific service name

    -Clean                         Stop and remove all containers and volumes

  Testing:
    -Test                          Run tests
      -TestService <service>         Specific service (gateway/ingestion/books/auth/user-data/recommendation)

  Help:
    -Help                          Show this help message

EXAMPLES:

  .\scripts.ps1 -CompileProto
  .\scripts.ps1 -CreateAdmin -Email admin@minsik.com -Password securepass123
  .\scripts.ps1 -Deploy
  .\scripts.ps1 -Deploy -Environment prod
  .\scripts.ps1 -Migrate
  .\scripts.ps1 -Logs -LogService books-service
  .\scripts.ps1 -Test -TestService books
  .\scripts.ps1 -Clean

"@ -ForegroundColor $ColorInfo
}

function Get-EnvFile {
    # .env holds the real credentials this machine's volumes were initialised
    # with; .env.example is only the fallback for a fresh checkout. Preferring
    # the example file silently breaks against an existing database volume.
    if (Test-Path ".env") {
        return ".env"
    }
    return ".env.example"
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
        },
        @{
            Source = "proto/recommendation.proto"
            Destinations = @("services/recommendation/app/proto", "services/gateway/app/proto")
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
            $content = $content -replace "(?m)^import ${protoBaseName}_pb2", "from . import ${protoBaseName}_pb2"
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

function Connect-Registry {
    param(
        [string]$Registry,
        [string]$Username = "",
        [string]$Password = ""
    )

    Write-Host "  Authenticating with $Registry..." -ForegroundColor Gray

    if ($Username -and $Password) {
        $Password | & docker login $Registry --username $Username --password-stdin
    } else {
        & docker login $Registry
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Error-Message "Docker login to $Registry failed"
        return $false
    }

    return $true
}

function Build-And-Push-Images {
    param(
        [string]$Registry,
        [string]$Username = "",
        [string]$Password = ""
    )

    $services = @(
        @{ Name = "Auth Service";           Dockerfile = "services/auth/Dockerfile";           ImageName = "auth-service" },
        @{ Name = "Gateway Service";        Dockerfile = "services/gateway/Dockerfile";        ImageName = "gateway-service" },
        @{ Name = "Ingestion Service";      Dockerfile = "services/ingestion/Dockerfile";      ImageName = "ingestion-service" },
        @{ Name = "Books Service";          Dockerfile = "services/books/Dockerfile";          ImageName = "books-service" },
        @{ Name = "User Data Service";      Dockerfile = "services/user_data/Dockerfile";      ImageName = "user-data-service" },
        @{ Name = "Recommendation Service"; Dockerfile = "services/recommendation/Dockerfile"; ImageName = "recommendation-service" },
        @{ Name = "DB Migrator";            Dockerfile = "services/db_migrator/Dockerfile";    ImageName = "db-migrator" },
        @{ Name = "RQ Worker";              Dockerfile = "services/ingestion/Dockerfile";      ImageName = "rq-worker" },
        @{ Name = "Frontend";               Dockerfile = "../Minsik-web/Dockerfile";          ImageName = "frontend"; Context = "../Minsik-web" }
    )

    Write-Step "Building and pushing images to $Registry..."

    $loginResult = Connect-Registry -Registry $Registry -Username $Username -Password $Password
    if (-not $loginResult) {
        return $false
    }

    foreach ($service in $services) {
        $imageTag = "$Registry/$($service.ImageName):latest"

        Write-Host "  Building $($service.Name)..." -ForegroundColor Gray

        if (-not (Test-Path $service.Dockerfile)) {
            Write-Error-Message "Dockerfile not found at $($service.Dockerfile)"
            return $false
        }

        $absoluteDockerfilePath = (Resolve-Path $service.Dockerfile).Path

        # The frontend lives in a sibling repo directory, so it needs its own
        # build context rather than the server root.
        $buildContext = "."
        if ($service.Context) {
            $buildContext = (Resolve-Path $service.Context).Path
        }

        & docker build -t $imageTag -f $absoluteDockerfilePath $buildContext

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

function Run-Migrations {
    Write-Step "Running database migrations..."

    if (-not (Test-Path ".env")) {
        Write-Warning-Message ".env file not found"
        return
    }

    & docker-compose --env-file (Get-EnvFile) run --rm db-migrator

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Database migrations completed successfully!"
    } else {
        Write-Error-Message "Database migrations failed (exit code $LASTEXITCODE)"
    }
}

function Deploy-Services {
    param(
        [string]$Environment = "dev"
    )

    if ($Environment -eq "dev") {
        Write-Step "Starting development environment..."

        & docker-compose --env-file (Get-EnvFile) up -d --build

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Development environment started!"
            & docker-compose --env-file (Get-EnvFile) ps
        } else {
            Write-Error-Message "Failed to start development environment"
        }

    } elseif ($Environment -eq "prod") {
        Write-Error-Message "Production deploy requires credentials. Use scripts.private.ps1 instead."

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
        & docker-compose --env-file (Get-EnvFile) logs -f $Service
    } else {
        & docker-compose --env-file (Get-EnvFile) logs -f
    }
}

function Run-Tests {
    param(
        [string]$Service
    )

    Write-Step "Running tests..."

    $serviceMap = @{
        "gateway"        = "gateway-service"
        "ingestion"      = "ingestion-service"
        "books"          = "books-service"
        "auth"           = "auth-service"
        "user-data"      = "user-data-service"
        "recommendation" = "recommendation-service"
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
        $services = @("gateway", "ingestion", "books", "auth", "user-data", "recommendation")
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

    & docker-compose --env-file (Get-EnvFile) down -v
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
if ($Migrate)      { Run-Migrations }
if ($Logs)         { Show-Logs -Service $LogService }
if ($Test)         { Run-Tests -Service $TestService }
if ($Clean)        { Clean-All }
