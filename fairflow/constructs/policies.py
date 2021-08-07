from typing import List

from aws_cdk import (
    core as cdk,
    aws_iam as iam
)

class PolicyConstruct(cdk.Construct):

    def __init__(self, scope: cdk.Construct, id: str,
                       efs_arn: str, s3_logs_bucket_arn: str,
                       rds_secret_arn: str, cluster_arn: str,
                       external_task_arns: List[str], external_tasks_log_group_arn: str):
        super().__init__(scope, id)

        stack = cdk.Stack.of(self)
        secrets_wildcard_arn = f'arn:aws:secretsmanager:{stack.region}:{stack.account}:secret:airflow-*'

        # Example
        self.managed_policies: List[iam.IManagedPolicy] = [
            # iam.ManagedPolicy.from_aws_managed_policy_name('CloudWatchLogsReadOnlyAccess')
        ]

        self.policy_statements: List[iam.PolicyStatement] = [
            # Permission to mount our EFS on an access point
            iam.PolicyStatement(
                actions = ["elasticfilesystem:ClientMount",
                           "elasticfilesystem:ClientWrite",
                           "elasticfilesystem:DescribeMountTargets",
                           'elasticfilesystem:DescribeFileSystems',
                           'elasticfilesystem:DescribeAccessPoints'],
                effect = iam.Effect.ALLOW,
                resources = [efs_arn]
            ),
            # Permission to log to our S3 bucket
            iam.PolicyStatement(
                actions = ["s3:*"],
                effect = iam.Effect.ALLOW,
                resources = [f'{s3_logs_bucket_arn}/*']
            ),
            iam.PolicyStatement(
                actions = ["s3:ListBucket"],
                effect = iam.Effect.ALLOW,
                resources = [f'{s3_logs_bucket_arn}']
            ),
            # Secrets access
            iam.PolicyStatement(
                actions = ["secretsmanager:GetResourcePolicy",
                           "secretsmanager:GetSecretValue",
                           "secretsmanager:DescribeSecret",
                           "secretsmanager:ListSecretVersionIds"],
                effect = iam.Effect.ALLOW,
                resources = [rds_secret_arn,
                             secrets_wildcard_arn]
            ),
            iam.PolicyStatement(
                actions = ["secretsmanager:ListSecrets"],
                effect = iam.Effect.ALLOW,
                resources = ["*"]
            ),
            # ECS policies for External Tasks
            iam.PolicyStatement(
                actions = ["ecs:Describe*",
                           "ecs:List*"],
                effect = iam.Effect.ALLOW,
                resources = external_task_arns
            ),
            iam.PolicyStatement(
                actions = ["ecs:DescribeContainerInstances",
                           "ecs:UpdateContainerAgent",
                           "ecs:DescribeTasks",
                           "ecs:ListTasks",
                           "ecs:StartTask",
                           "ecs:StopTask",
                           "ecs:RunTask"],
                effect = iam.Effect.ALLOW,
                resources = ["*"],
                conditions = {"ArnEquals": {"ecs:cluster": cluster_arn}}
            ),
            iam.PolicyStatement(
                actions = ["iam:PassRole"],
                effect = iam.Effect.ALLOW,
                resources = ["*"],
                conditions = {
                    "StringLike": {
                        "iam:PassedToService": "ecs-tasks.amazonaws.com"
                        }
                    }
            ),
            # The ECS Operator also needs to interact with the Cloud Watch logs
            iam.PolicyStatement(
                actions = ["logs:Describe*",
                           "logs:Get*",
                           "logs:List*",
                           "logs:StartQuery",
                           "logs:StopQuery",
                           "logs:TestMetricFilter",
                           "logs:FilterLogEvents"],
                effect = iam.Effect.ALLOW,
                resources = [external_tasks_log_group_arn]
            ),
        ]


    def attach_policies(self, role: iam.IRole) -> None:
        for managed_policy in self.managed_policies:
            role.add_managed_policy(managed_policy)

        for policy_statement in self.policy_statements:
            role.add_to_policy(policy_statement)
