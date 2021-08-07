from typing import List
from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
    aws_logs as logs,
)

from fairflow.constructs.contruct_properties import (
    ExternalTaskProps,
    ContainerInfo,
)
from fairflow.constructs.task_construct import ExternalTaskDefinition

class ExternalDagTasks(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str,
                       shared_volume: ecs.Volume,
                       mounting_point: ecs.MountPoint):
        super().__init__(scope, id)

        self.container_logging = ecs.AwsLogDriver(
            stream_prefix = 'FairflowExternalTask',
            log_group = logs.LogGroup(self, 'FairflowExternalTaskLogs',
                log_group_name = f'FairflowExternalTaskLogs-{cdk.Stack.of(self).stack_name}',
                retention = logs.RetentionDays.ONE_MONTH
            )
        )

        # What's interesting here, is we are defining Tasks, but not creating a service or
        #   specifying the cluster or VPC or anything like that.  From within Airflow, we will
        #   use the  ECSOperator and some environment variables we passed to Airflow about what
        #   cluster, security group, and (private) subnets to launch these tasks in

        # Task with more resources allocated
        self.big_task = ExternalTaskDefinition(self, 'FairflowBigTask',
            ExternalTaskProps(
                container_info = ContainerInfo(
                    asset_dir = './tasks/big_task',
                    name = 'BigTaskContainer'
                ),
                cpu = 1024,
                memory_limit_mib = 2048,
                task_family_name = f'BigGuys-{cdk.Stack.of(self).stack_name}',
                logging = self.container_logging,
                shared_volume = shared_volume,
                mounting_point = mounting_point
            )
        )

        # Task with less resources allocated
        self.little_task = ExternalTaskDefinition(self, 'FairflowLittleTask',
            ExternalTaskProps(
                container_info = ContainerInfo(
                    asset_dir = './tasks/little_task',
                    name = f'LittleTaskContainer'
                ),
                cpu = 256,
                memory_limit_mib = 512,
                task_family_name = f'LittleGuys-{cdk.Stack.of(self).stack_name}',
                logging = self.container_logging,
                shared_volume = shared_volume,
                mounting_point = mounting_point
            )
        )


    def get_external_task_arns(self) -> List[str]:
        external_task_arns: List[str] = []
        for task in [self.big_task, self.little_task]:
            external_task_arns.append(task.worker_task.task_definition_arn)

        return external_task_arns