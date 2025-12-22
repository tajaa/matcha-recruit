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

# Default values
PUSH_TO_ECR=true
TRIGGER_DEPLOY=false
PLATFORM="linux/arm64"
NO_CACHE=false

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
    --no-push          Build images locally without pushing to ECR
    --no-cache         Do not use cache when building the image
    --deploy           Trigger deployment after pushing (sets deploy flag)
    --platform ARCH    Target platform (default: linux/arm64)
    -h, --help         Show this help message

ENVIRONMENT VARIABLES (required):
    AWS_ACCOUNT_ID     AWS account ID for ECR (auto-detected if not set)
    AWS_REGION         AWS region (default: us-west-1)
    ECR_BACKEND_REPO   ECR repository name for backend (default: matcha-backend)
    ECR_FRONTEND_REPO  ECR repository name for frontend (default: matcha-frontend)

EXAMPLES:
    # Build and push to ECR
    $0

    # Build locally without pushing
    $0 --no-push

    # Build, push, and trigger deployment
    $0 --deploy
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

    log_info "Backend ECR URI: ${BACKEND_ECR_URI}"
    log_info "Frontend ECR URI: ${FRONTEND_ECR_URI}"

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

    local cache_args=()
    if [ "$NO_CACHE" = true ]; then
        cache_args+=("--no-cache")
        log_info "Building with --no-cache"
    fi

    if docker buildx build \
        --platform "$PLATFORM" \
        --load \
        "${tag_args[@]}" \
        ${cache_args[@]+"${cache_args[@]}"} \
        --build-arg "BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg "GIT_SHA=${git_sha}" \
        -f "$dockerfile_path" \
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

    # Build images
    build_backend
    build_frontend

    # Push images
    push_image "Backend" "${BACKEND_ECR_URI}"
    push_image "Frontend" "${FRONTEND_ECR_URI}"

    # Deployment trigger
    if [ "$TRIGGER_DEPLOY" = true ]; then
        log_section "Deployment Trigger"
        log_info "Deploy flag set - GitHub Actions will handle EC2 deployment"
        echo "DEPLOY=true" >> "$GITHUB_OUTPUT" 2>/dev/null || true
    fi

    log_section "Build Complete"
    log_success "All operations completed successfully!"
    log_info "Backend: ${BACKEND_ECR_URI}:latest"
    log_info "Frontend: ${FRONTEND_ECR_URI}:latest"
}

################################################################################
# Script Entry Point
################################################################################

parse_args "$@"
main
