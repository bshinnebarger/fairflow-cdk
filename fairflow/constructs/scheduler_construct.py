from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
)

from fairflow.constructs.contruct_properties import FairflowChildConstructProps
from fairflow.config import (
    SCHEDULER_TASK_CONFIG,
    SCHEDULER_CONFIG
)

class SchedulerConstruct(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str, props: FairflowChildConstructProps):
        super().__init__(scope, id)

        scheduler_task = ecs.FargateTaskDefinition(self, 'SchedulerTask',
            cpu = SCHEDULER_TASK_CONFIG.cpu,
            memory_limit_mib = SCHEDULER_TASK_CONFIG.memory_limit_mib,
            volumes = [props.shared_volume]
        )
        props.policies.attach_policies(scheduler_task.task_role)

        scheduler_task.add_container(SCHEDULER_CONFIG.name,
            container_name = SCHEDULER_CONFIG.name,
            image = ecs.ContainerImage.from_docker_image_asset(props.airflow_image),
            logging = props.logging,
            environment = props.env_vars,
            secrets = props.secret_env_vars,
            entry_point = SCHEDULER_CONFIG.entry_point,
            command = SCHEDULER_CONFIG.command,
            port_mappings = [ecs.PortMapping(container_port = SCHEDULER_CONFIG.container_port)]
        ).add_mount_points(props.mounting_point)

        desired_count = 2 if props.highly_available else 1

        self.scheduler_service = ecs.FargateService(self, 'SchedulerService',
            cluster = props.cluster,
            task_definition = scheduler_task,
            security_group = props.vpc_props.default_vpc_security_group,
            platform_version = ecs.FargatePlatformVersion.VERSION1_4,
            desired_count = desired_count
        )
