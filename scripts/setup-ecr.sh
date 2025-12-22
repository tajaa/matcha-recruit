#!/bin/bash

################################################################################
# Matcha-Recruit ECR Repository Setup Script
# Creates ECR repositories for backend and frontend images
# Run this once before first deployment
################################################################################

set -e

# Color codes
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m'

# Default values
AWS_REGION="${AWS_REGION:-us-west-1}"
BACKEND_REPO="matcha-backend"
FRONTEND_REPO="matcha-frontend"

echo -e "${BLUE}[INFO]${NC} Setting up ECR repositories in region: ${AWS_REGION}"

# Create backend repository
echo -e "${BLUE}[INFO]${NC} Creating repository: ${BACKEND_REPO}"
aws ecr create-repository \
    --repository-name "${BACKEND_REPO}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    2>/dev/null || echo -e "${YELLOW}[WARN]${NC} Repository ${BACKEND_REPO} already exists"

# Create frontend repository
echo -e "${BLUE}[INFO]${NC} Creating repository: ${FRONTEND_REPO}"
aws ecr create-repository \
    --repository-name "${FRONTEND_REPO}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    2>/dev/null || echo -e "${YELLOW}[WARN]${NC} Repository ${FRONTEND_REPO} already exists"

# Set lifecycle policy to clean up old images (keep last 10)
LIFECYCLE_POLICY='{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 images",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}'

echo -e "${BLUE}[INFO]${NC} Setting lifecycle policy for ${BACKEND_REPO}"
aws ecr put-lifecycle-policy \
    --repository-name "${BACKEND_REPO}" \
    --region "${AWS_REGION}" \
    --lifecycle-policy-text "${LIFECYCLE_POLICY}" \
    2>/dev/null || echo -e "${YELLOW}[WARN]${NC} Failed to set lifecycle policy for ${BACKEND_REPO}"

echo -e "${BLUE}[INFO]${NC} Setting lifecycle policy for ${FRONTEND_REPO}"
aws ecr put-lifecycle-policy \
    --repository-name "${FRONTEND_REPO}" \
    --region "${AWS_REGION}" \
    --lifecycle-policy-text "${LIFECYCLE_POLICY}" \
    2>/dev/null || echo -e "${YELLOW}[WARN]${NC} Failed to set lifecycle policy for ${FRONTEND_REPO}"

# Get account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo -e "\n${GREEN}[SUCCESS]${NC} ECR repositories created!"
echo -e "${BLUE}[INFO]${NC} Backend: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${BACKEND_REPO}"
echo -e "${BLUE}[INFO]${NC} Frontend: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${FRONTEND_REPO}"
