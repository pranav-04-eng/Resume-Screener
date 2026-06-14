#!/usr/bin/env bash
# Provisions S3 + DynamoDB + SQS in LocalStack to mirror the real AWS resources.
# Runs automatically inside the LocalStack container (init/ready.d) and is also
# safe to run by hand:  bash scripts/init-localstack.sh
set -euo pipefail

# Inside the container `awslocal` exists; from the host fall back to aws+endpoint.
if command -v awslocal >/dev/null 2>&1; then
  aws_cmd() { awslocal "$@"; }
else
  export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
  aws_cmd() { aws --endpoint-url "${AWS_ENDPOINT_URL:-http://localhost:4566}" "$@"; }
fi

BUCKET="resume-screener-files"
TABLE="resume-screener"
QUEUE="resume-screener-jobs"
DLQ="resume-screener-jobs-dlq"

echo "==> S3 bucket: $BUCKET"
aws_cmd s3api create-bucket --bucket "$BUCKET" 2>/dev/null || true
# CORS so the browser can PUT directly via pre-signed URLs.
aws_cmd s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration '{
  "CORSRules": [{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"]
  }]
}'

echo "==> DynamoDB table: $TABLE (single-table + GSI1)"
aws_cmd dynamodb create-table \
  --table-name "$TABLE" \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=GSI1PK,AttributeType=S \
    AttributeName=GSI1SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes '[{
    "IndexName": "GSI1",
    "KeySchema": [
      {"AttributeName": "GSI1PK", "KeyType": "HASH"},
      {"AttributeName": "GSI1SK", "KeyType": "RANGE"}
    ],
    "Projection": {"ProjectionType": "ALL"}
  }]' \
  --billing-mode PAY_PER_REQUEST 2>/dev/null || true

echo "==> SQS queues: $QUEUE (+ DLQ $DLQ)"
aws_cmd sqs create-queue --queue-name "$DLQ" 2>/dev/null || true
DLQ_ARN=$(aws_cmd sqs get-queue-attributes \
  --queue-url "$(aws_cmd sqs get-queue-url --queue-name "$DLQ" --query QueueUrl --output text)" \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
aws_cmd sqs create-queue --queue-name "$QUEUE" --attributes '{
  "VisibilityTimeout": "300",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"'"$DLQ_ARN"'\",\"maxReceiveCount\":\"3\"}"
}' 2>/dev/null || true

echo "==> LocalStack bootstrap complete."
