#!/usr/bin/env bash
# One-time AWS setup for the backend. Idempotent enough to re-run.
#   AWS_PROFILE=... OPENAI_API_KEY=... [ANTHROPIC_API_KEY=...] ./scripts/aws/bootstrap.sh
# Creates: ECR repo, S3 bucket for the DuckDB snapshot, Secrets Manager secrets for the
# model keys you pass (OpenAI, Claude or both), IAM roles, and an App Runner service that auto-deploys new :latest images.
set -euo pipefail

REGION="${AWS_REGION:-eu-central-1}"
NAME="adobee-hive"
REPO="$NAME-backend"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${HIVE_BUCKET:-$NAME-data-$ACCOUNT}"
IMAGE="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
[ -n "${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}" ] ||
  { echo "set OPENAI_API_KEY and/or ANTHROPIC_API_KEY (they go to Secrets Manager, never into the repo)" >&2; exit 1; }
# Shared secrets for the team: owner edits and demo reset. Generated unless you pass your own.
OWNER_EDIT_TOKEN="${OWNER_EDIT_TOKEN:-$(openssl rand -hex 16)}"
DEMO_RESET_TOKEN="${DEMO_RESET_TOKEN:-$(openssl rand -hex 16)}"

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

# put_secret NAME VALUE: create or update a Secrets Manager secret and print its ARN.
put_secret() {
  local arn
  arn=$(aws secretsmanager describe-secret --secret-id "$1" --region "$REGION" --query ARN --output text 2>/dev/null || true)
  if [ -z "$arn" ]; then
    arn=$(aws secretsmanager create-secret --name "$1" --secret-string "$2" --region "$REGION" --query ARN --output text)
  else
    aws secretsmanager put-secret-value --secret-id "$1" --secret-string "$2" --region "$REGION" >/dev/null
  fi
  echo "$arn"
}

echo "==> Secrets for the API keys"
SECRET_ARNS=""
APP_SECRETS=""
# add_secret ENV_NAME SECRET_NAME VALUE: store one key and wire it into App Runner as ENV_NAME.
add_secret() {
  local arn
  arn=$(put_secret "$2" "$3")
  SECRET_ARNS="${SECRET_ARNS:+$SECRET_ARNS, }\"$arn\""
  APP_SECRETS="${APP_SECRETS:+$APP_SECRETS, }\"$1\": \"$arn\""
}
[ -z "${OPENAI_API_KEY:-}" ] || add_secret OPENAI_API_KEY "$NAME/openai" "$OPENAI_API_KEY"
[ -z "${ANTHROPIC_API_KEY:-}" ] || add_secret ANTHROPIC_API_KEY "$NAME/anthropic" "$ANTHROPIC_API_KEY"

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
    {\"Effect\": \"Allow\", \"Action\": \"secretsmanager:GetSecretValue\", \"Resource\": [$SECRET_ARNS]}
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
          \"RuntimeEnvironmentVariables\": {\"DUCKDB_S3_URI\": \"s3://$BUCKET/abh.duckdb\", \"CORS_ORIGINS\": \"*\",
            \"OWNER_EDIT_TOKEN\": \"$OWNER_EDIT_TOKEN\", \"DEMO_RESET_TOKEN\": \"$DEMO_RESET_TOKEN\"},
          \"RuntimeEnvironmentSecrets\": {$APP_SECRETS}
        }
      }
    }" --query Service.ServiceArn --output text)
fi

URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" --query Service.ServiceUrl --output text)
echo
echo "Backend:   https://$URL   (MCP for agents: https://$URL/mcp/)"
echo "Owner token (owner studio edits): $OWNER_EDIT_TOKEN"
echo "Demo token (X-Demo-Token for /api/demo/reset): $DEMO_RESET_TOKEN"
echo "Share both with the team in person or a password manager, never in the repo or chat."
echo "Next: in Amplify set VITE_API_URL=https://$URL, then push to main."
