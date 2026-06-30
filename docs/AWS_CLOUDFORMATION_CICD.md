# AWS CloudFormation CI/CD for Stock Market Agent

This project now has two CloudFormation options.

## Option 1: Add CI/CD to the existing AWS deployment

Use this when ECR, ECS, RDS, S3, and the Streamlit app already exist.

Template:

```text
infra/cloudformation/codepipeline-existing-resources.yml
```

Parameter example:

```text
infra/cloudformation/codepipeline-existing-parameters.example.json
```

This creates only the CI/CD layer:

- S3 artifact bucket for CodePipeline artifacts.
- CodeBuild project.
- CodeBuild IAM role.
- CodePipeline IAM role.
- CodePipeline with Source, Build, and Deploy stages.
- CloudWatch log group for build logs.

It uses the existing resources:

```text
ECR repo: dev-dstrmaysam-stock-market-agent-repo
ECS cluster: dev-dstrmaysam-stock-market-agent-cluster
ECS service: dev-dstrmaysam-stock-market-agent-service
Container name: stock-market-agent
```

## Option 2: Create full infrastructure

Use this only for a fresh environment, because it creates ECR, ECS, RDS,
Secrets Manager, CodeBuild, optional CodePipeline, S3, IAM, security groups,
and CloudWatch.

Template:

```text
infra/cloudformation/stock-market-agent.yml
```

Parameter example:

```text
infra/cloudformation/parameters.dev.example.json
```

Important: do not run the full stack against an account where resources with
the same names already exist unless you plan to import or rename resources.

## CI/CD flow

```text
Developer pushes code to GitHub main
  -> CodePipeline Source stage detects the change
  -> CodeBuild installs dependencies
  -> CodeBuild runs tests
  -> CodeBuild builds Docker image
  -> CodeBuild pushes image to Amazon ECR
  -> CodeBuild creates imagedefinitions.json
  -> CodePipeline ECS Deploy stage updates ECS service
  -> ECS starts a new Streamlit task with the new image
```

## Required one-time AWS setup

Create and authorize a GitHub CodeStar Connection in AWS Console:

```text
Developer Tools -> Connections -> Create connection -> GitHub
```

Copy the connection ARN and replace:

```text
arn:aws:codestar-connections:eu-west-2:666127452756:connection/REPLACE_WITH_CONNECTION_ID
```

in:

```text
infra/cloudformation/codepipeline-existing-parameters.example.json
```

Save the edited file as:

```text
infra/cloudformation/codepipeline-existing-parameters.json
```

## Create the pipeline stack

From the project root:

```powershell
aws cloudformation create-stack `
  --stack-name dev-dstrmaysam-stock-market-agent-pipeline `
  --template-body file://infra/cloudformation/codepipeline-existing-resources.yml `
  --parameters file://infra/cloudformation/codepipeline-existing-parameters.json `
  --capabilities CAPABILITY_NAMED_IAM `
  --region eu-west-2
```

Wait for completion:

```powershell
aws cloudformation wait stack-create-complete `
  --stack-name dev-dstrmaysam-stock-market-agent-pipeline `
  --region eu-west-2
```

Check outputs:

```powershell
aws cloudformation describe-stacks `
  --stack-name dev-dstrmaysam-stock-market-agent-pipeline `
  --query "Stacks[0].Outputs" `
  --region eu-west-2
```

## Update the pipeline stack

```powershell
aws cloudformation update-stack `
  --stack-name dev-dstrmaysam-stock-market-agent-pipeline `
  --template-body file://infra/cloudformation/codepipeline-existing-resources.yml `
  --parameters file://infra/cloudformation/codepipeline-existing-parameters.json `
  --capabilities CAPABILITY_NAMED_IAM `
  --region eu-west-2
```

## Buildspec behavior

CodeBuild uses:

```text
buildspec.yml
```

The buildspec:

1. Logs in to Amazon ECR.
2. Installs Python dependencies.
3. Runs tests with `pytest`.
4. Builds the Docker image.
5. Tags the image with the Git commit hash and `latest`.
6. Pushes both tags to ECR.
7. Writes `imagedefinitions.json` for ECS deploy.

## How ECS deploy knows what to update

The ECS deploy action reads:

```text
imagedefinitions.json
```

Example:

```json
[
  {
    "name": "stock-market-agent",
    "imageUri": "666127452756.dkr.ecr.eu-west-2.amazonaws.com/dev-dstrmaysam-stock-market-agent-repo:abc123"
  }
]
```

The `name` must match the ECS container name in the task definition:

```text
stock-market-agent
```

## Rollback

If a deployment fails, ECS keeps the previous healthy task running. To roll back
manually, redeploy a previous ECR image tag or use the previous task definition
revision from ECS.

## Notifications

Email updates can be added later with:

- Amazon SNS topic.
- CodePipeline notification rule.
- Subscriber email address.

This is not required for the core deployment pipeline, but it is recommended
for production.
