#!/bin/bash

################################################################################
# Matcha-Recruit Build and Push Script
# Builds and pushes Docker images for backend and frontend to AWS ECR
# Supports ARM64 architecture for AWS Graviton instances
################################################################################

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly MAGENTA='\033[0;35m'
readonly NC='\033[0m' # No Color

# Script configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly BACKEND_DIR="${SCRIPT_DIR}/server"
readonly FRONTEND_DIR="${SCRIPT_DIR}/client"
readonly GUMMFIT_BACKEND_DIR="${SCRIPT_DIR}/gummfit-agency/server"
readonly GUMMFIT_FRONTEND_DIR="${SCRIPT_DIR}/gummfit-agency/client"

# Default values
PUSH_TO_ECR=true
TRIGGER_DEPLOY=false
PLATFORM="linux/arm64"
NO_CACHE=false
BUILD_BACKEND=true
BUILD_FRONTEND=true
BUILD_GUMMFIT_BACKEND=false
BUILD_GUMMFIT_FRONTEND=false

################################################################################
# Helper Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo -e "\n${MAGENTA}========================================${NC}"
    echo -e "${MAGENTA}$1${NC}"
    echo -e "${MAGENTA}========================================${NC}\n"
}

# Print usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Build and push Docker images for Matcha-Recruit backend and frontend.

OPTIONS:
    --no-push              Build images locally without pushing to ECR
    --no-cache             Do not use cache when building the image
    --deploy               Trigger deployment after pushing (sets deploy flag)
    --platform ARCH        Target platform (default: linux/arm64)
    --backend-only         Build only the matcha backend image
    --frontend-only        Build only the matcha frontend image
    --gummfit-backend      Also build the gummfit backend image
    --gummfit-frontend     Also build the gummfit frontend image
    --gummfit              Build both gummfit images (backend + frontend)
    --all                  Build all images (matcha + gummfit)
    -h, --help             Show this help message

ENVIRONMENT VARIABLES (required):
    AWS_ACCOUNT_ID             AWS account ID for ECR (auto-detected if not set)
    AWS_REGION                 AWS region (default: us-west-1)
    ECR_BACKEND_REPO           ECR repository name for matcha backend (default: matcha-backend)
    ECR_FRONTEND_REPO          ECR repository name for matcha frontend (default: matcha-frontend)
    ECR_GUMMFIT_BACKEND_REPO   ECR repository name for gummfit backend (default: gummfit-backend)
    ECR_GUMMFIT_FRONTEND_REPO  ECR repository name for gummfit frontend (default: gummfit-frontend)

EXAMPLES:
    # Build and push matcha to ECR (default)
    $0

    # Build locally without pushing
    $0 --no-push

    # Build, push, and trigger deployment
    $0 --deploy

    # Build only the matcha backend
    $0 --backend-only

    # Build all services (matcha + gummfit)
    $0 --all

    # Build only gummfit services
    $0 --gummfit

    # Build gummfit backend alongside matcha
    $0 --gummfit-backend
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-push)
                PUSH_TO_ECR=false
                shift
                ;;
            --no-cache)
                NO_CACHE=true
                shift
                ;;
            --deploy)
                TRIGGER_DEPLOY=true
                shift
                ;;
            --backend-only)
                BUILD_FRONTEND=false
                shift
                ;;
            --frontend-only)
                BUILD_BACKEND=false
                shift
                ;;
            --gummfit-backend)
                BUILD_GUMMFIT_BACKEND=true
                shift
                ;;
            --gummfit-frontend)
                BUILD_GUMMFIT_FRONTEND=true
                shift
                ;;
            --gummfit)
                BUILD_GUMMFIT_BACKEND=true
                BUILD_GUMMFIT_FRONTEND=true
                shift
                ;;
            --all)
                BUILD_BACKEND=true
                BUILD_FRONTEND=true
                BUILD_GUMMFIT_BACKEND=true
                BUILD_GUMMFIT_FRONTEND=true
                shift
                ;;
            --platform)
                PLATFORM="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

# Validate required tools
validate_tools() {
    log_section "Validating Required Tools"

    local required_tools=("docker" "aws" "git")
    local missing_tools=()

    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
            log_error "$tool is not installed"
        else
            log_info "$tool is installed: $(command -v $tool)"
        fi
    done

    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        exit 1
    fi

    # Check Docker daemon
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi

    log_success "All required tools are available"
}

# Validate environment variables
validate_env() {
    log_section "Validating Environment Variables"

    # Set defaults
    export AWS_REGION="${AWS_REGION:-us-west-1}"
    export ECR_BACKEND_REPO="${ECR_BACKEND_REPO:-matcha-backend}"
    export ECR_FRONTEND_REPO="${ECR_FRONTEND_REPO:-matcha-frontend}"
    export ECR_GUMMFIT_BACKEND_REPO="${ECR_GUMMFIT_BACKEND_REPO:-gummfit-backend}"
    export ECR_GUMMFIT_FRONTEND_REPO="${ECR_GUMMFIT_FRONTEND_REPO:-gummfit-frontend}"

    # Auto-fetch AWS Account ID if not set
    if [ -z "${AWS_ACCOUNT_ID:-}" ]; then
        log_info "AWS_ACCOUNT_ID not set, fetching from AWS CLI..."
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
        if [ -z "${AWS_ACCOUNT_ID}" ]; then
            log_error "Failed to fetch AWS_ACCOUNT_ID automatically. Please set it manually or configure AWS CLI."
            exit 1
        fi
        export AWS_ACCOUNT_ID
        log_success "Auto-detected AWS_ACCOUNT_ID: ${AWS_ACCOUNT_ID}"
    else
        log_info "AWS_ACCOUNT_ID is set: ${AWS_ACCOUNT_ID}"
    fi

    # Construct ECR URIs
    export BACKEND_ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_BACKEND_REPO}"
    export FRONTEND_ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_FRONTEND_REPO}"
    export GUMMFIT_BACKEND_ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_GUMMFIT_BACKEND_REPO}"
    export GUMMFIT_FRONTEND_ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_GUMMFIT_FRONTEND_REPO}"

    log_info "Backend ECR URI: ${BACKEND_ECR_URI}"
    log_info "Frontend ECR URI: ${FRONTEND_ECR_URI}"
    if [ "$BUILD_GUMMFIT_BACKEND" = true ]; then
        log_info "GumFit Backend ECR URI: ${GUMMFIT_BACKEND_ECR_URI}"
    fi
    if [ "$BUILD_GUMMFIT_FRONTEND" = true ]; then
        log_info "GumFit Frontend ECR URI: ${GUMMFIT_FRONTEND_ECR_URI}"
    fi

    log_success "Environment validation complete"
}

# Login to ECR
ecr_login() {
    log_section "Authenticating with ECR"

    if [ "$PUSH_TO_ECR" = false ]; then
        log_warning "Skipping ECR login (--no-push flag set)"
        return 0
    fi

    log_info "Logging in to ECR in region: ${AWS_REGION}"

    if aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"; then
        log_success "Successfully authenticated with ECR"
    else
        log_error "Failed to authenticate with ECR"
        exit 1
    fi
}

# Build Docker image
build_image() {
    local name=$1
    local dockerfile_path=$2
    local context_dir=$3
    local image_uri=$4

    log_section "Building $name Image"

    log_info "Context: $context_dir"
    log_info "Dockerfile: $dockerfile_path"
    log_info "Platform: $PLATFORM"

    # Generate Git commit SHA for tagging
    local git_sha
    git_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    local tags=(
        "${image_uri}:latest"
        "${image_uri}:${git_sha}"
    )

    # Build tag arguments
    local tag_args=()
    for tag in "${tags[@]}"; do
        tag_args+=(-t "$tag")
        log_info "Tag: $tag"
    done

    # Build the image
    log_info "Starting Docker build..."

    local build_args=(
        --platform "$PLATFORM"
        --load
        "${tag_args[@]}"
        --build-arg "BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        --build-arg "GIT_SHA=${git_sha}"
        --build-arg "BUILDKIT_INLINE_CACHE=1"
        -f "$dockerfile_path"
    )

    # Add cache flags unless --no-cache is set
    if [ "$NO_CACHE" = true ]; then
        build_args+=("--no-cache")
        log_info "Building with --no-cache"
    elif [ "$PUSH_TO_ECR" = true ]; then
        # Use registry cache for cross-platform builds (requires ECR auth)
        # image-manifest=true and oci-mediatypes=true required for ECR compatibility
        build_args+=(
            --cache-from "type=registry,ref=${image_uri}:buildcache"
            --cache-to "type=registry,ref=${image_uri}:buildcache,mode=max,image-manifest=true,oci-mediatypes=true"
        )
        log_info "Using registry cache: ${image_uri}:buildcache"
    else
        log_info "Local build - using default Docker cache"
    fi

    if docker buildx build \
        "${build_args[@]}" \
        "$context_dir"; then
        log_success "$name image built successfully"
    else
        log_error "Failed to build $name image"
        exit 1
    fi
}

# Push Docker image
push_image() {
    local name=$1
    local image_uri=$2

    if [ "$PUSH_TO_ECR" = false ]; then
        log_warning "Skipping push for $name (--no-push flag set)"
        return 0
    fi

    log_section "Pushing $name Image to ECR"

    local git_sha
    git_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    local tags=(
        "${image_uri}:latest"
        "${image_uri}:${git_sha}"
    )

    for tag in "${tags[@]}"; do
        log_info "Pushing: $tag"
        if docker push "$tag"; then
            log_success "Pushed: $tag"
        else
            log_error "Failed to push: $tag"
            exit 1
        fi
    done
}

# Build backend
build_backend() {
    build_image \
        "Backend" \
        "${BACKEND_DIR}/Dockerfile" \
        "${BACKEND_DIR}" \
        "${BACKEND_ECR_URI}"
}

# Build frontend
build_frontend() {
    build_image \
        "Frontend" \
        "${FRONTEND_DIR}/Dockerfile" \
        "${FRONTEND_DIR}" \
        "${FRONTEND_ECR_URI}"
}

# Build gummfit backend
build_gummfit_backend() {
    build_image \
        "GumFit Backend" \
        "${GUMMFIT_BACKEND_DIR}/Dockerfile" \
        "${GUMMFIT_BACKEND_DIR}" \
        "${GUMMFIT_BACKEND_ECR_URI}"
}

# Build gummfit frontend
build_gummfit_frontend() {
    build_image \
        "GumFit Frontend" \
        "${GUMMFIT_FRONTEND_DIR}/Dockerfile" \
        "${GUMMFIT_FRONTEND_DIR}" \
        "${GUMMFIT_FRONTEND_ECR_URI}"
}

# Main execution
main() {
    log_section "Matcha-Recruit Build & Push Script"
    log_info "Platform: $PLATFORM"
    log_info "Push to ECR: $PUSH_TO_ECR"
    log_info "Trigger Deploy: $TRIGGER_DEPLOY"

    # Validate environment
    validate_tools
    validate_env

    # Authenticate with ECR
    ecr_login

    # Build images in parallel
    local pids=()
    local services=()

    if [ "$BUILD_BACKEND" = true ]; then
        build_backend &
        pids+=($!)
        services+=("Backend")
    else
        log_warning "Skipping backend build (--frontend-only)"
    fi

    if [ "$BUILD_FRONTEND" = true ]; then
        build_frontend &
        pids+=($!)
        services+=("Frontend")
    else
        log_warning "Skipping frontend build (--backend-only)"
    fi

    if [ "$BUILD_GUMMFIT_BACKEND" = true ]; then
        build_gummfit_backend &
        pids+=($!)
        services+=("GumFit Backend")
    fi

    if [ "$BUILD_GUMMFIT_FRONTEND" = true ]; then
        build_gummfit_frontend &
        pids+=($!)
        services+=("GumFit Frontend")
    fi

    # Wait for all builds to complete
    local failed=false
    for i in "${!pids[@]}"; do
        if ! wait "${pids[$i]}"; then
            log_error "${services[$i]} build failed"
            failed=true
        fi
    done

    if [ "$failed" = true ]; then
        log_error "One or more builds failed"
        exit 1
    fi

    # Push images (only after all builds succeed to preserve atomicity)
    if [ "$BUILD_BACKEND" = true ]; then
        push_image "Backend" "${BACKEND_ECR_URI}"
    fi
    if [ "$BUILD_FRONTEND" = true ]; then
        push_image "Frontend" "${FRONTEND_ECR_URI}"
    fi
    if [ "$BUILD_GUMMFIT_BACKEND" = true ]; then
        push_image "GumFit Backend" "${GUMMFIT_BACKEND_ECR_URI}"
    fi
    if [ "$BUILD_GUMMFIT_FRONTEND" = true ]; then
        push_image "GumFit Frontend" "${GUMMFIT_FRONTEND_ECR_URI}"
    fi

    # Deployment trigger
    if [ "$TRIGGER_DEPLOY" = true ]; then
        log_section "Deployment Trigger"
        log_info "Deploy flag set - GitHub Actions will handle EC2 deployment"
        echo "DEPLOY=true" >> "$GITHUB_OUTPUT" 2>/dev/null || true
    fi

    log_section "Build Complete"
    log_success "All operations completed successfully!"
    if [ "$BUILD_BACKEND" = true ]; then
        log_info "Backend: ${BACKEND_ECR_URI}:latest"
    fi
    if [ "$BUILD_FRONTEND" = true ]; then
        log_info "Frontend: ${FRONTEND_ECR_URI}:latest"
    fi
    if [ "$BUILD_GUMMFIT_BACKEND" = true ]; then
        log_info "GumFit Backend: ${GUMMFIT_BACKEND_ECR_URI}:latest"
    fi
    if [ "$BUILD_GUMMFIT_FRONTEND" = true ]; then
        log_info "GumFit Frontend: ${GUMMFIT_FRONTEND_ECR_URI}:latest"
    fi
}

################################################################################
# Script Entry Point
################################################################################

parse_args "$@"

if [ "$BUILD_BACKEND" = false ] && [ "$BUILD_FRONTEND" = false ]; then
    log_error "--backend-only and --frontend-only cannot be used together"
    exit 1
fi

main
