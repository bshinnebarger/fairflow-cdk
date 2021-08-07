from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
    aws_iam as iam
)

from fairflow.constructs.contruct_properties import FairflowChildConstructProps
from fairflow.config import (
    WORKER_AUTOSCALING_CONFIG,
    WORKER_CONFIG,
    WORKER_TASK_CONFIG
)

class WorkerConstruct(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str, props: FairflowChildConstructProps):
        super().__init__(scope, id)

        worker_task = ecs.FargateTaskDefinition(self, 'WorkerTask',
            cpu = WORKER_TASK_CONFIG.cpu,
            memory_limit_mib = WORKER_TASK_CONFIG.memory_limit_mib,
            volumes = [props.shared_volume]
        )
        props.policies.attach_policies(worker_task.task_role)

        worker_task.add_container(WORKER_CONFIG.name,
            container_name = WORKER_CONFIG.name,
            image = ecs.ContainerImage.from_docker_image_asset(props.airflow_image),
            logging = props.logging,
            environment = props.env_vars,
            secrets = props.secret_env_vars,
            entry_point = WORKER_CONFIG.entry_point,
            command = WORKER_CONFIG.command,
            port_mappings = [ecs.PortMapping(container_port = WORKER_CONFIG.container_port)]
        ).add_mount_points(props.mounting_point)

        desired_count = 2 if props.highly_available else 1

        self.worker_service = ecs.FargateService(self, 'WorkerService',
            cluster = props.cluster,
            task_definition = worker_task,
            security_group = props.vpc_props.default_vpc_security_group,
            platform_version = ecs.FargatePlatformVersion.VERSION1_4,
            desired_count = desired_count
        )

        if props.enable_autoscaling:
            self.configure_auto_scaling()


    def configure_auto_scaling(self) -> None:
        scaling = self.worker_service.auto_scale_task_count(
            max_capacity = WORKER_AUTOSCALING_CONFIG.max_task_count,
            min_capacity = WORKER_AUTOSCALING_CONFIG.min_task_count
        )

        if WORKER_AUTOSCALING_CONFIG.cpu_usage_percent:
            scaling.scale_on_cpu_utilization('CpuScaling',
                target_utilization_percent = WORKER_AUTOSCALING_CONFIG.cpu_usage_percent,
                scale_in_cooldown = cdk.Duration.seconds(300),
                scale_out_cooldown = cdk.Duration.seconds(60)
            )

        if WORKER_AUTOSCALING_CONFIG.mem_usage_percent:
            scaling.scale_on_memory_utilization('MemoryScaling',
                target_utilization_percent = WORKER_AUTOSCALING_CONFIG.mem_usage_percent,
                scale_in_cooldown = cdk.Duration.seconds(300),
                scale_out_cooldown = cdk.Duration.seconds(60)
            )
