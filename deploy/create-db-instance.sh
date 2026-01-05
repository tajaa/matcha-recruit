#!/bin/bash
set -e

# Configuration
AMI_ID="ami-0437f9b314bca719f" # Amazon Linux 2023 ARM64 (us-west-1)
INSTANCE_TYPE="t4g.micro"
KEY_NAME="roonMT-arm"
SG_NAME="matcha-db-sg"
REGION="us-west-1"

echo "Creating Security Group..."
# Check if SG exists
SG_ID=$(aws ec2 describe-security-groups --group-names "$SG_NAME" --region "$REGION" --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || true)

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group --group-name "$SG_NAME" --description "Security group for Matcha PostgreSQL DB" --region "$REGION" --query 'GroupId' --output text)
    echo "Created SG: $SG_ID"
    
    # Allow SSH
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0 --region "$REGION"
    
else
    echo "SG $SG_NAME already exists ($SG_ID)"
fi

echo "Ensuring Ingress Rules..."
# Allow SSH (22)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0 --region "$REGION" 2>/dev/null || echo "SSH rule likely already exists"

# Allow Postgres (5432)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 5432 --cidr 0.0.0.0/0 --region "$REGION" 2>/dev/null || echo "Postgres rule likely already exists"

echo "Generating User Data..."
cat <<EOF > user_data.sh
#!/bin/bash
yum update -y
yum install -y docker
service docker start
usermod -a -G docker ec2-user
systemctl enable docker

# Create a docker network
docker network create matcha-network

# Run Postgres
# We use the same credentials as local dev for now, but these should be rotated in production
docker run -d \
    --name matcha-postgres \
    --restart unless-stopped \
    -p 5432:5432 \
    -e POSTGRES_USER=matcha \
    -e POSTGRES_PASSWORD=matcha_dev \
    -e POSTGRES_DB=matcha \
    -v matcha_postgres_data:/var/lib/postgresql/data \
    pgvector/pgvector:pg15

# Install system dependencies for backups (AWS CLI is usually pre-installed on AL2023 but good to check)
yum install -y cronie
systemctl start crond
systemctl enable crond
EOF

echo "Launching Instance..."
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --count 1 \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --user-data file://user_data.sh \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=matcha-postgres-db}]' \
    --region "$REGION" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "Instance launched: $INSTANCE_ID"
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "--------------------------------------------------"
echo "Database Instance Ready!"
echo "Instance ID: $INSTANCE_ID"
echo "Public IP:   $PUBLIC_IP"
echo "SSH Command: ssh -i $KEY_NAME.pem ec2-user@$PUBLIC_IP"
echo "--------------------------------------------------"
echo "NOTE: Docker installation and container startup happens in background."
echo "Wait 2-3 minutes before attempting to connect to Postgres."

rm user_data.sh
