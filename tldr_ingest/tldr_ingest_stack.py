from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class TldrIngestStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # S3 bucket for summaries and audio (lifecycle: delete after 30 days)
        artifacts_bucket = s3.Bucket(
            self,
            "TldrArtifactsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    enabled=True,
                    expiration=Duration.days(30),
                )
            ],
        )

        # Lambda layer for beautifulsoup4 and lxml (built separately; see lambda/README or build script)
        deps_layer = _lambda.LayerVersion(
            self,
            "TldrDepsLayer",
            code=_lambda.Code.from_asset("lambda_layer"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="BeautifulSoup4 and lxml for TLDR parser",
        )

        # Lambda function
        fn = _lambda.Function(
            self,
            "TldrPipelineFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.minutes(5),
            memory_size=512,
            layers=[deps_layer],
            environment={
                "ARTIFACTS_BUCKET": artifacts_bucket.bucket_name,
                "GMAIL_SECRET_NAME": "tldr-bot/gmail-app-password",
                "GMAIL_ADDRESS_SECRET_NAME": "tldr-bot/gmail-address",
                "SLACK_SECRET_NAME": "tldr-bot/slack-webhook-url",
            },
        )

        # Permissions: S3 read/write
        artifacts_bucket.grant_read_write(fn)

        # Permissions: Secrets Manager (read tldr-bot secrets)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:tldr-bot*"],
            )
        )

        # Permissions: Bedrock InvokeModel
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["*"],
            )
        )

        # Permissions: Polly SynthesizeSpeech (sync only; Polly does not support assume-role in trust policy)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["polly:SynthesizeSpeech"],
                resources=["*"],
            )
        )

        # CloudWatch Events: run daily at 7:30 AM UTC (adjust as needed)
        daily_rule = events.Rule(
            self,
            "TldrDailyRule",
            schedule=events.Schedule.cron(minute="30", hour="7"),
            description="Trigger TLDR pipeline daily",
        )
        daily_rule.add_target(targets.LambdaFunction(fn))
