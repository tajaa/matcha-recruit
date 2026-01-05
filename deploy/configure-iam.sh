#!/bin/bash
set -e

ROLE_NAME="MatchaDBBackupRole"
POLICY_NAME="MatchaDBBackupS3Policy"
PROFILE_NAME="MatchaDBBackupProfile"
INSTANCE_ID="i-01dfbc6406175dc87" # Hardcoded from previous step, or pass as arg
REGION="us-west-1"

# 1. Create Trust Policy
cat <<EOF > trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# 2. Create Role
echo "Creating/Checking Role $ROLE_NAME..."
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    echo "  Role exists."
else
    aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file://trust-policy.json
    echo "  Role created."
fi

# 3. Create Permissions Policy
cat <<EOF > s3-policy.json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::matcha-recruit-backups",
                "arn:aws:s3:::matcha-recruit-backups/*"
            ]
        }
    ]
}
EOF

echo "Creating/Checking Policy $POLICY_NAME..."
# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$POLICY_NAME"

if aws iam get-policy --policy-arn "$POLICY_ARN" >/dev/null 2>&1; then
    echo "  Policy exists."
    # Update it just in case
    aws iam create-policy-version --policy-arn "$POLICY_ARN" --policy-document file://s3-policy.json --set-as-default >/dev/null 2>&1 || true
else
    aws iam create-policy --policy-name "$POLICY_NAME" --policy-document file://s3-policy.json
    echo "  Policy created."
fi

# 4. Attach Policy to Role
echo "Attaching Policy to Role..."
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$POLICY_ARN"

# 5. Create Instance Profile
echo "Creating/Checking Instance Profile $PROFILE_NAME..."
if aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
    echo "  Profile exists."
else
    aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME"
    echo "  Profile created."
fi

# 6. Add Role to Profile
echo "Adding Role to Profile..."
aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME" 2>/dev/null || echo "  Role probably already in profile."

# 7. Associate with Instance
echo "Associating Profile with Instance $INSTANCE_ID..."
# Check if already associated
ASSOC_ID=$(aws ec2 describe-iam-instance-profile-associations --filters Name=instance-id,Values="$INSTANCE_ID" --region "$REGION" --query "IamInstanceProfileAssociations[0].AssociationId" --output text)

if [ "$ASSOC_ID" == "None" ]; then
    # Wait for profile to propagate (it takes a few seconds)
    echo "  Waiting for IAM propagation..."
    sleep 10
    aws ec2 associate-iam-instance-profile --instance-id "$INSTANCE_ID" --iam-instance-profile Name="$PROFILE_NAME" --region "$REGION"
    echo "  Associated!"
else
    echo "  Instance already has a profile association: $ASSOC_ID"
    # Ideally check if it's the RIGHT profile, but for now assume yes or we'd need to replace it
fi

rm trust-policy.json s3-policy.json
echo "IAM Configuration Complete."
