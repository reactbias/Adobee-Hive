#!/usr/bin/env bash
# One-time AWS setup for the backend. Idempotent enough to re-run.
#   AWS_PROFILE=... ANTHROPIC_API_KEY=sk-ant-... ./scripts/aws/bootstrap.sh
# Creates: ECR repo, S3 bucket for the DuckDB snapshot, Secrets Manager secret for the
# Claude key, IAM roles, and an App Runner service that auto-deploys new :latest images.
set -euo pipefail

REGION="${AWS_REGION:-eu-central-1}"
NAME="adobee-hive"
REPO="$NAME-backend"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${HIVE_BUCKET:-$NAME-data-$ACCOUNT}"
IMAGE="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY (it goes to Secrets Manager, never into the repo)}"

echo "==> ECR repository $REPO"
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 ||
  aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null

echo "==> First image push (later pushes come from GitHub Actions)"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${IMAGE%%/*}"
docker build --platform linux/amd64 -t "$IMAGE" "$(dirname "$0")/../../backend"
docker push "$IMAGE"

echo "==> S3 bucket $BUCKET"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null ||
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null

echo "==> Secret for the Claude API key"
SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "$NAME/anthropic" --region "$REGION" --query ARN --output text 2>/dev/null || true)
if [ -z "$SECRET_ARN" ]; then
  SECRET_ARN=$(aws secretsmanager create-secret --name "$NAME/anthropic" --secret-string "$ANTHROPIC_API_KEY" \
    --region "$REGION" --query ARN --output text)
else
  aws secretsmanager put-secret-value --secret-id "$NAME/anthropic" --secret-string "$ANTHROPIC_API_KEY" --region "$REGION" >/dev/null
fi

echo "==> IAM roles"
ACCESS_ROLE="$NAME-apprunner-ecr"
INSTANCE_ROLE="$NAME-apprunner-instance"
aws iam get-role --role-name "$ACCESS_ROLE" >/dev/null 2>&1 || {
  aws iam create-role --role-name "$ACCESS_ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ACCESS_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
  sleep 10  # IAM propagation
}
aws iam get-role --role-name "$INSTANCE_ROLE" >/dev/null 2>&1 ||
  aws iam create-role --role-name "$INSTANCE_ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
aws iam put-role-policy --role-name "$INSTANCE_ROLE" --policy-name "$NAME-runtime" --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\", \"Action\": [\"s3:GetObject\", \"s3:PutObject\"], \"Resource\": \"arn:aws:s3:::$BUCKET/*\"},
    {\"Effect\": \"Allow\", \"Action\": \"secretsmanager:GetSecretValue\", \"Resource\": \"$SECRET_ARN\"}
  ]}"
ACCESS_ARN=$(aws iam get-role --role-name "$ACCESS_ROLE" --query Role.Arn --output text)
INSTANCE_ARN=$(aws iam get-role --role-name "$INSTANCE_ROLE" --query Role.Arn --output text)

echo "==> App Runner service (one instance: DuckDB is a single file)"
SERVICE_ARN=$(aws apprunner list-services --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='$NAME'].ServiceArn" --output text)
if [ -z "$SERVICE_ARN" ]; then
  ASG_ARN=$(aws apprunner create-auto-scaling-configuration --region "$REGION" \
    --auto-scaling-configuration-name "$NAME-single" --min-size 1 --max-size 1 \
    --query AutoScalingConfiguration.AutoScalingConfigurationArn --output text)
  SERVICE_ARN=$(aws apprunner create-service --region "$REGION" --service-name "$NAME" \
    --auto-scaling-configuration-arn "$ASG_ARN" \
    --instance-configuration "Cpu=1024,Memory=2048,InstanceRoleArn=$INSTANCE_ARN" \
    --health-check-configuration "Protocol=HTTP,Path=/api/health" \
    --source-configuration "{
      \"AutoDeploymentsEnabled\": true,
      \"AuthenticationConfiguration\": {\"AccessRoleArn\": \"$ACCESS_ARN\"},
      \"ImageRepository\": {
        \"ImageIdentifier\": \"$IMAGE\",
        \"ImageRepositoryType\": \"ECR\",
        \"ImageConfiguration\": {
          \"Port\": \"8000\",
          \"RuntimeEnvironmentVariables\": {\"DUCKDB_S3_URI\": \"s3://$BUCKET/abh.duckdb\", \"CORS_ORIGINS\": \"*\"},
          \"RuntimeEnvironmentSecrets\": {\"ANTHROPIC_API_KEY\": \"$SECRET_ARN\"}
        }
      }
    }" --query Service.ServiceArn --output text)
fi

URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" --query Service.ServiceUrl --output text)
echo
echo "Backend:   https://$URL   (MCP for agents: https://$URL/mcp/)"
echo "Next: in Amplify set VITE_API_URL=https://$URL, then push to main."
