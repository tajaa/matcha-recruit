# GitHub Actions OIDC role for deploy.yml

Lets `.github/workflows/deploy.yml`'s build job push images to ECR without a
long-lived AWS access key stored in GitHub. The deploy job (SSH to EC2) needs
no AWS credentials at all — ECR login for the pull happens on the host with
the host's own credentials, same as a laptop deploy.

## One-time bootstrap (run from repo root)

```bash
# 1. OIDC provider for GitHub Actions (account-wide, not repo-specific — skip
#    if one already exists for token.actions.githubusercontent.com)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# 2. Role, trust-scoped to this repo (any ref — tighten to refs/heads/main
#    in trust-policy.json's `sub` condition if you want deploys gated to main)
aws iam create-role \
  --role-name github-actions-matcha \
  --assume-role-policy-document file://deploy/github-oidc/trust-policy.json \
  --description "GitHub Actions OIDC role for tajaa/matcha-recruit deploy workflow (ECR push only)"

# 3. Inline policy — ECR push/pull on matcha-backend + matcha-frontend only
aws iam put-role-policy \
  --role-name github-actions-matcha \
  --policy-name ecr-push \
  --policy-document file://deploy/github-oidc/ecr-push-policy.json
```

## GitHub secrets

```bash
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::010438494410:role/github-actions-matcha"
gh secret set EC2_SSH_KEY < secrets/roonMT-arm.pem
```

`AWS_ACCOUNT_ID` is not a secret — it's already hardcoded in `scripts/update-ec2.sh`. `EC2_INSTANCE_ID` isn't needed (deploy job uses SSH, not SSM).

## Rotating the PEM

If `secrets/roonMT-arm.pem` is ever rotated, re-run the `gh secret set EC2_SSH_KEY` command above with the new key. Nothing else changes.

## Verify

```bash
aws iam get-role --role-name github-actions-matcha --query 'Role.Arn'
aws iam list-open-id-connect-providers
gh secret list   # should show AWS_ROLE_ARN and EC2_SSH_KEY
```
