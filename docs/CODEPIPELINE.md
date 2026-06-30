# AWS CodePipeline Deployment Plan

This project uses AWS CodePipeline instead of GitHub Actions.

## Pipeline stages

```text
Source
  -> Build and test in CodeBuild
  -> Push Docker image to ECR
  -> Deploy image to ECS Fargate
```

## Required AWS resources

- CodePipeline pipeline.
- CodeBuild project.
- ECR repository.
- ECS cluster and service.
- S3 artifact bucket.
- IAM role for CodePipeline.
- IAM role for CodeBuild.
- CloudWatch log group.

## Build process

CodeBuild uses `buildspec.yml`.

Steps:

1. Login to Amazon ECR.
2. Install Python dependencies.
3. Run tests.
4. Build Docker image.
5. Push Docker image to ECR.
6. Create `imagedefinitions.json`.
7. ECS deploy stage updates the running service.

## ECS container

The ECS service runs the Streamlit app on port `8501`.

Health check path:

```text
/_stcore/health
```
