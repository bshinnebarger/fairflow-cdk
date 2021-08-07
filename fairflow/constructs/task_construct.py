from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets
)
from fairflow.constructs.contruct_properties import ExternalTaskProps

class ExternalTaskDefinition(cdk.Construct):
    def __init__(self, scope: cdk.Construct, task_name: str, props: ExternalTaskProps):
        super().__init__(scope, f'{task_name}-TaskConstruct')

        self.worker_task = ecs.FargateTaskDefinition(self, f'{task_name}-TaskDef',
            cpu = props.cpu,
            memory_limit_mib = props.memory_limit_mib,
            family = props.task_family_name,
            volumes = [props.shared_volume]
        )

        worker_image_asset = ecr_assets.DockerImageAsset(self, f'{props.container_info.name}-BuildImage',
            directory = props.container_info.asset_dir
        )

        self.worker_task.add_container(props.container_info.name,
            image = ecs.ContainerImage.from_docker_image_asset(worker_image_asset),
            logging = props.logging
        ).add_mount_points(props.mounting_point)
