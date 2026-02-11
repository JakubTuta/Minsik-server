# ============================================================================
# Minsik Development Automation Scripts
# ============================================================================
# PowerShell script for common development tasks:
# - Compile Protocol Buffer files
# - Create admin/user accounts
# - Deploy services (dev/prod)
# - Database migrations
# - Run tests
# ============================================================================

param(
    [switch]$Help,
    [switch]$CompileProto,
    [switch]$CreateAdmin,
    [string]$Email,
    [string]$Password,
    [switch]$CreateUser,
    [switch]$Deploy,
    [string]$Environment = "dev",
    [switch]$Migrate,
    [string]$MigrateAction = "upgrade",
    [switch]$Test,
    [string]$TestService,
    [switch]$Logs,
    [string]$LogService,
    [switch]$Clean,
    [switch]$Init
)

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

    -CreateUser                    Create a regular user
      -Email <email>                 User email address
      -Password <password>           User password

  Deployment:
    -Deploy                        Deploy services
      -Environment <env>             Environment (dev/prod, default: dev)

    -Logs                          View service logs
      -LogService <service>          Specific service (postgres/redis/gateway/ingestion/books/auth/user-data)

    -Clean                         Stop and remove all containers and volumes

  Database:
    -Migrate                       Run database migrations
      -MigrateAction <action>        Action (upgrade/downgrade/current, default: upgrade)

    -Init                          Initialize database schemas

  Testing:
    -Test                          Run tests
      -TestService <service>         Test specific service (gateway/ingestion/books/all)

  Help:
    -Help                          Show this help message

EXAMPLES:

  # Compile Protocol Buffers
  .\scripts.ps1 -CompileProto

  # Create admin user
  .\scripts.ps1 -CreateAdmin -Email admin@minsik.com -Password securepass123

  # Create regular user
  .\scripts.ps1 -CreateUser -Email user@minsik.com -Password userpass123

  # Deploy to development
  .\scripts.ps1 -Deploy

  # Deploy to production
  .\scripts.ps1 -Deploy -Environment prod

  # View all logs
  .\scripts.ps1 -Logs

  # View specific service logs
  .\scripts.ps1 -Logs -LogService postgres

  # Run database migrations
  .\scripts.ps1 -Migrate

  # Initialize database schemas
  .\scripts.ps1 -Init

  # Run all tests
  .\scripts.ps1 -Test

  # Test specific service
  .\scripts.ps1 -Test -TestService books

  # Clean everything (WARNING: Deletes data!)
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

    # Check if proto directory exists
    if (-not (Test-Path "proto")) {
        Write-Error-Message "proto/ directory not found"
        return
    }

    # Static proto file definitions
    # Format: @{Source = "proto file path"; Destinations = @("output directory 1", "output directory 2")}
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
            # Create destination directory if it doesn't exist
            if (-not (Test-Path $destination)) {
                New-Item -ItemType Directory -Force -Path $destination | Out-Null
            }

            # Create __init__.py to make it a proper Python package
            $initFile = Join-Path $destination "__init__.py"
            if (-not (Test-Path $initFile)) {
                New-Item -ItemType File -Path $initFile -Force | Out-Null
            }

            # Get base name without extension for the proto file
            $protoBaseName = [System.IO.Path]::GetFileNameWithoutExtension($protoFile)

            # Compile proto file to current directory first
            python -m grpc_tools.protoc `
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

            # Move generated files to destination
            Move-Item -Path "${protoBaseName}_pb2.py" -Destination $destination -Force
            Move-Item -Path "${protoBaseName}_pb2_grpc.py" -Destination $destination -Force
            Move-Item -Path "${protoBaseName}_pb2.pyi" -Destination $destination -Force

            # Fix imports in the grpc file to use relative imports
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

    # Check if create_admin.py exists
    if (-not (Test-Path "scripts/create_admin.py")) {
        Write-Warning-Message "scripts/create_admin.py not found, creating it..."

        # Create the Python script
        New-Item -ItemType Directory -Force -Path "scripts" | Out-Null

        $createAdminScript = @"
import asyncio
import sys
import argparse
from passlib.hash import bcrypt
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

async def create_admin(email: str, password: str):
    # Database connection
    db_url = os.getenv('DATABASE_URL') or f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Hash password
        password_hash = bcrypt.hash(password)

        # Insert admin user (raw SQL for simplicity)
        await session.execute(
            '''
            INSERT INTO auth.users (email, password_hash, role, is_verified, is_active)
            VALUES (:email, :password_hash, 'admin', true, true)
            ON CONFLICT (email) DO UPDATE SET
                password_hash = :password_hash,
                role = 'admin'
            ''',
            {'email': email, 'password_hash': password_hash}
        )
        await session.commit()

    print(f'Admin user created: {email}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True)
    args = parser.parse_args()

    asyncio.run(create_admin(args.email, args.password))
"@
        Set-Content -Path "scripts/create_admin.py" -Value $createAdminScript
    }

    # Run the Python script
    python scripts/create_admin.py --email $Email --password $Password

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Admin user created successfully!"
    } else {
        Write-Error-Message "Failed to create admin user"
    }
}

function Create-Regular-User {
    param(
        [string]$Email,
        [string]$Password
    )

    if (-not $Email -or -not $Password) {
        Write-Error-Message "Email and Password are required"
        Write-Host "Usage: .\scripts.ps1 -CreateUser -Email user@minsik.com -Password password" -ForegroundColor $ColorWarning
        return
    }

    Write-Step "Creating regular user: $Email"

    # Similar to create admin but with role='user'
    Write-Warning-Message "User creation not implemented yet (Sprint 2 feature)"
    Write-Host "  For now, users will be created via registration API in Sprint 2" -ForegroundColor Gray
}

function Build-And-Push-Images {
    $GAR_REGISTRY = "europe-central2-docker.pkg.dev/minsik-486117/server"

    # Service definitions: name, dockerfile path, image name
    $services = @(
        @{
            Name = "Gateway Service"
            Dockerfile = "services/gateway/Dockerfile"
            ImageName = "gateway-service"
        },
        @{
            Name = "Ingestion Service"
            Dockerfile = "services/ingestion/Dockerfile"
            ImageName = "ingestion-service"
        },
        @{
            Name = "Books Service"
            Dockerfile = "services/books/Dockerfile"
            ImageName = "books-service"
        },
        @{
            Name = "RQ Worker"
            Dockerfile = "services/ingestion/Dockerfile"
            ImageName = "rq-worker"
        }
    )

    Write-Step "Building and pushing images to Google Artifact Registry..."

    # Configure Docker to use gcloud credentials
    Write-Host "  Configuring Docker authentication..." -ForegroundColor Gray
    gcloud auth configure-docker europe-central2-docker.pkg.dev --quiet

    if ($LASTEXITCODE -ne 0) {
        Write-Error-Message "Failed to configure Docker authentication. Make sure you're logged in with 'gcloud auth login'"
        return $false
    }

    foreach ($service in $services) {
        $imageName = "$GAR_REGISTRY/$($service.ImageName)"
        $imageTag = "$imageName:latest"

        Write-Host "  Building $($service.Name)..." -ForegroundColor Gray

        docker build -t $imageTag -f $service.Dockerfile .

        if ($LASTEXITCODE -ne 0) {
            Write-Error-Message "Failed to build $($service.Name)"
            return $false
        }

        Write-Host "  Pushing $($service.Name) to GAR..." -ForegroundColor Gray
        docker push $imageTag

        if ($LASTEXITCODE -ne 0) {
            Write-Error-Message "Failed to push $($service.Name)"
            return $false
        }

        Write-Host "    Pushed: $imageTag" -ForegroundColor Green
    }

    Write-Success "All images built and pushed successfully!"
    return $true
}

function Deploy-Services {
    param(
        [string]$Environment = "dev"
    )

    Write-Step "Deploying services to $Environment environment..."

    # Check if .env exists
    if (-not (Test-Path ".env")) {
        Write-Warning-Message ".env file not found, copying from .env.example..."
        Copy-Item ".env.example" ".env"
    }

    if ($Environment -eq "dev") {
        Write-Host "  Using docker-compose.yml (development)" -ForegroundColor Gray
        docker-compose up -d --build
    } elseif ($Environment -eq "prod") {
        Write-Host "  Using docker-compose.prod.yml (production)" -ForegroundColor Gray

        # Build and push images to GAR for production
        $buildSuccess = Build-And-Push-Images

        if (-not $buildSuccess) {
            Write-Error-Message "Image build/push failed. Deployment aborted."
            return
        }

        # Pull images from GAR and deploy
        Write-Host "`n  Pulling images from GAR and deploying..." -ForegroundColor Gray
        docker-compose -f docker-compose.prod.yml pull
        docker-compose -f docker-compose.prod.yml up -d
    } else {
        Write-Error-Message "Invalid environment: $Environment (use 'dev' or 'prod')"
        return
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Deployment complete!"
        Write-Host "`nService Status:" -ForegroundColor $ColorInfo
        if ($Environment -eq "dev") {
            docker-compose ps
        } else {
            docker-compose -f docker-compose.prod.yml ps
        }
    } else {
        Write-Error-Message "Deployment failed"
    }
}

function Show-Logs {
    param(
        [string]$Service
    )

    Write-Step "Viewing logs..."

    if ($Service) {
        Write-Host "  Service: $Service" -ForegroundColor Gray
        docker-compose logs -f $Service
    } else {
        Write-Host "  All services (Ctrl+C to exit)" -ForegroundColor Gray
        docker-compose logs -f
    }
}

function Run-Migration {
    param(
        [string]$Action = "upgrade"
    )

    Write-Step "Running database migrations: $Action"

    # Services with Alembic migrations and their container names
    $migrationServices = @(
        @{ Service = "ingestion";  Container = "minsik-ingestion-service-dev" },
        @{ Service = "auth";       Container = "minsik-auth-service-dev" },
        @{ Service = "user-data";  Container = "minsik-user-data-service-dev" }
    )

    $alembicAction = switch ($Action) {
        "upgrade"   { "upgrade head" }
        "downgrade" { "downgrade -1" }
        "current"   { "current" }
        "history"   { "history" }
        default     { "upgrade head" }
    }

    foreach ($svc in $migrationServices) {
        $containerName = $svc.Container
        $serviceName = $svc.Service

        if (-not (docker ps -q -f name=$containerName)) {
            Write-Warning-Message "Container $containerName is not running -- skipping $serviceName migrations"
            continue
        }

        Write-Host "  Running '$alembicAction' for $serviceName..." -ForegroundColor Gray
        docker exec $containerName sh -c "alembic $alembicAction"

        if ($LASTEXITCODE -eq 0) {
            Write-Success "  $serviceName migrations OK"
        } else {
            Write-Error-Message "  $serviceName migrations FAILED"
        }
    }
}

function Initialize-Database {
    Write-Step "Initializing database schemas..."

    Write-Host "  Running init-db.sql script..." -ForegroundColor Gray

    # Run the init script through docker
    docker exec minsik-postgres-dev psql -U postgres -d minsik_db -f /docker-entrypoint-initdb.d/init-db.sql

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Database initialized!"
    } else {
        Write-Error-Message "Database initialization failed"
    }
}

function Run-Tests {
    param(
        [string]$Service,
        [switch]$Coverage,
        [string]$TestFile
    )

    Write-Step "Running tests..."

    # Service name mapping
    $serviceMap = @{
        "gateway"   = "gateway-service"
        "ingestion" = "ingestion-service"
        "books"     = "books-service"
        "auth"      = "auth-service"
        "user-data" = "user-data-service"
    }

    if ($Service -and $Service -ne "all") {
        $containerName = "minsik-$($serviceMap[$Service])-dev"

        if (-not (docker ps -q -f name=$containerName)) {
            Write-Warning-Message "Service container not running. Starting services..."
            docker-compose up -d $($serviceMap[$Service])
            Start-Sleep -Seconds 5
        }

        Write-Host "  Service: $Service" -ForegroundColor Gray

        # Build pytest command
        $pytestCmd = "pytest"

        if ($TestFile) {
            $pytestCmd += " tests/$TestFile"
        } else {
            $pytestCmd += " tests/"
        }

        $pytestCmd += " -v"

        if ($Coverage) {
            $pytestCmd += " --cov=app --cov-report=term-missing --cov-report=html"
        }

        Write-Host "  Running: $pytestCmd" -ForegroundColor Gray

        docker exec $containerName sh -c "$pytestCmd"

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Tests passed!"
        } else {
            Write-Error-Message "Tests failed"
        }

    } else {
        Write-Host "  All services" -ForegroundColor Gray

        # Run tests for all implemented services
        $services = @("gateway", "ingestion", "books", "auth", "user-data")
        $totalPassed = 0
        $totalFailed = 0

        foreach ($svc in $services) {
            Write-Host "`n  Testing $svc service..." -ForegroundColor $ColorInfo

            $containerName = "minsik-$($serviceMap[$svc])-dev"

            if (-not (docker ps -q -f name=$containerName)) {
                Write-Warning-Message "Service container not running. Skipping $svc..."
                continue
            }

            docker exec $containerName pytest tests/ -v

            if ($LASTEXITCODE -eq 0) {
                $totalPassed++
                Write-Success "$svc tests passed"
            } else {
                $totalFailed++
                Write-Error-Message "$svc tests failed"
            }
        }

        Write-Host "`nTest Summary:" -ForegroundColor $ColorInfo
        Write-Host "  Passed: $totalPassed" -ForegroundColor Green
        Write-Host "  Failed: $totalFailed" -ForegroundColor $(if ($totalFailed -gt 0) { "Red" } else { "Gray" })
    }
}

function Clean-All {
    Write-Warning-Message "This will stop and remove all containers and volumes!"
    $confirmation = Read-Host "Are you sure? (yes/no)"

    if ($confirmation -ne "yes") {
        Write-Host "Cancelled" -ForegroundColor Gray
        return
    }

    Write-Step "Stopping services..."
    docker-compose down -v

    Write-Step "Removing volumes..."
    docker volume prune -f

    Write-Success "Cleanup complete!"
}

# ============================================================================
# Main Execution
# ============================================================================

# If no parameters, show help
if ($PSBoundParameters.Count -eq 0) {
    Show-Help
    exit
}

# Execute commands
if ($Help) {
    Show-Help
}

if ($CompileProto) {
    Compile-Proto
}

if ($CreateAdmin) {
    Create-Admin-User -Email $Email -Password $Password
}

if ($CreateUser) {
    Create-Regular-User -Email $Email -Password $Password
}

if ($Deploy) {
    Deploy-Services -Environment $Environment
}

if ($Logs) {
    Show-Logs -Service $LogService
}

if ($Migrate) {
    Run-Migration -Action $MigrateAction
}

if ($Init) {
    Initialize-Database
}

if ($Test) {
    Run-Tests -Service $TestService
}

if ($Clean) {
    Clean-All
}
