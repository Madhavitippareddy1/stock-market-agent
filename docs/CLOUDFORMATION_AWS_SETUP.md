# CloudFormation AWS Setup

This project uses AWS CloudFormation for infrastructure as code.

CloudFormation files are in:

```text
infra/cloudformation/
```

For the current already-running AWS deployment, prefer the pipeline-only
template:

```text
infra/cloudformation/codepipeline-existing-resources.yml
```

That template creates CodePipeline and CodeBuild for the existing ECR/ECS
resources without trying to recreate the running app infrastructure.

Detailed CI/CD setup:

```text
docs/AWS_CLOUDFORMATION_CICD.md
```

## What CloudFormation creates

- Amazon ECR repository.
- Amazon ECS Fargate cluster.
- Amazon ECS service.
- ECS task definition.
- Amazon RDS PostgreSQL database.
- AWS Secrets Manager secret for RDS credentials.
- ECS task execution role.
- ECS task role.
- Security group for Streamlit port `8501`.
- Security group allowing ECS to reach RDS on port `5432`.
- CloudWatch log groups.
- S3 bucket for CodePipeline artifacts.
- CodeBuild project.
- Optional CodePipeline connected to GitHub through CodeStar Connections.

All created resources include the required capstone tag:

```text
dstrmaysam=dstrmaysam
```

## What CloudFormation does not create yet

These are expected as existing inputs or future phases:

- VPC and subnets.
- Application Load Balancer.
- Route 53 domain.
- ACM HTTPS certificate.
- Amazon Cognito authentication.
- OpenSearch Serverless collection.
- S3 financial reports bucket.

## Required setup

Copy the example parameters:

```bash
copy infra\cloudformation\parameters.example.json infra\cloudformation\parameters.json
```

Update:

```json
{
  "ParameterKey": "VpcId",
  "ParameterValue": "vpc-..."
}
```

and:

```json
{
  "ParameterKey": "SubnetIds",
  "ParameterValue": "subnet-...,subnet-..."
}
```

Also update private database subnets for RDS:

```json
{
  "ParameterKey": "DatabaseSubnetIds",
  "ParameterValue": "subnet-private-1,subnet-private-2"
}
```

RDS is created as private/internal only:

```text
PubliclyAccessible: false
ECS security group -> RDS security group on port 5432
```

For ECS production, do not use localhost for the MCP URL. Use the real shared
MCP server endpoint:

```json
{
  "ParameterKey": "McpServerUrl",
  "ParameterValue": "http://internal-dstrmaysam-shared-mcp-alb-748190876.eu-west-2.elb.amazonaws.com/sse"
}
```

For the AWS deployment, the common MCP server is exposed on the internal shared ALB:

```text
http://internal-dstrmaysam-shared-mcp-alb-748190876.eu-west-2.elb.amazonaws.com/sse
```

## Optional CodePipeline source

To create CodePipeline, fill:

```json
{
  "ParameterKey": "GitHubOwner",
  "ParameterValue": "your-github-user"
}
```

```json
{
  "ParameterKey": "GitHubRepo",
  "ParameterValue": "your-repo-name"
}
```

```json
{
  "ParameterKey": "CodeStarConnectionArn",
  "ParameterValue": "arn:aws:codestar-connections:..."
}
```

The CodeStar connection must be created and authorized in the AWS Console.

If those values are empty, the stack still creates ECR, ECS, CodeBuild, IAM,
S3, RDS, Secrets Manager, and CloudWatch, but skips CodePipeline.

## Deploy commands

From the project root:

```bash
aws cloudformation create-stack ^
  --template-body file://infra/cloudformation/stock-market-agent.yml ^
  --stack-name dev-stock-market-agent ^
  --parameters file://infra/cloudformation/parameters.json ^
  --capabilities CAPABILITY_NAMED_IAM
```

For later updates:

```bash
aws cloudformation update-stack ^
  --template-body file://infra/cloudformation/stock-market-agent.yml ^
  --stack-name dev-stock-market-agent ^
  --parameters file://infra/cloudformation/parameters.json ^
  --capabilities CAPABILITY_NAMED_IAM
```

To inspect outputs:

```bash
aws cloudformation describe-stacks ^
  --stack-name dev-stock-market-agent ^
  --query "Stacks[0].Outputs"
```

## Deployment flow

```text
GitHub source
  -> CodePipeline
  -> CodeBuild
  -> Docker build
  -> Push image to ECR
  -> ECS deploy
  -> Streamlit app runs on Fargate
```

## Security note

For early testing, the template allows port `8501` from `0.0.0.0/0`.

For safer deployment, change:

```json
{
  "ParameterKey": "AllowedIngressCidr",
  "ParameterValue": "YOUR_PUBLIC_IP/32"
}
```

For production, place ECS behind an Application Load Balancer and use HTTPS.
