from aws_cdk import (
    core as cdk,
    aws_efs as efs,
    aws_ecs as ecs
)
from fairflow.constructs.contruct_properties import VpcProps

class EfsConstruct(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str, vpc_props: VpcProps):
        super().__init__(scope, id)

        shared_fs = efs.FileSystem(self, 'SharedEFS',
            vpc = vpc_props.vpc,
            security_group = vpc_props.default_vpc_security_group,
            removal_policy = cdk.RemovalPolicy.DESTROY
        )
        shared_fs.connections.allow_default_port_from(
            other = vpc_props.default_vpc_security_group,
            description = 'EFS Ingress'
        )
        self.file_system_arn = shared_fs.file_system_arn
        cdk.CfnOutput(self, 'EfsFileSystemArn',
            value = shared_fs.file_system_arn,
            description = 'Shared EFS ARN'
        )

        # See README -> EFS Construct for more details about this
        access_point = shared_fs.add_access_point('DagsAccessPoint',
            create_acl = efs.Acl(
                owner_gid = '0',
                owner_uid = '50000',
                permissions = '755'
            ),
            path = "/fairflow",
            posix_user = efs.PosixUser(
                gid = '0',
                uid = '50000'
            )
        )

        # The Docker assets under the ./tasks folder are defaulting to the
        #   normal root user uid=0, gid=0, and they also have no need for the
        #   DAG definitions because they are self-contained Docker images,
        #   so I'm configuring another access point
        external_task_access_point = shared_fs.add_access_point('ExternalTaskAccessPoint',
            create_acl = efs.Acl(
                owner_gid = '0',
                owner_uid = '0',
                permissions = '755'
            ),
            path = "/fairflow-external",
        )

        self.shared_volume = ecs.Volume(
            name = 'fairflow',
            efs_volume_configuration = ecs.EfsVolumeConfiguration(
                file_system_id = shared_fs.file_system_id,
                authorization_config = ecs.AuthorizationConfig(
                    access_point_id = access_point.access_point_id,
                ),
                transit_encryption = 'ENABLED'
            )
        )

        self.shared_external_task_volume = ecs.Volume(
            name = 'fairflow-external',
            efs_volume_configuration = ecs.EfsVolumeConfiguration(
                file_system_id = shared_fs.file_system_id,
                authorization_config = ecs.AuthorizationConfig(
                    access_point_id = external_task_access_point.access_point_id,
                ),
                transit_encryption = 'ENABLED'
            )
        )

        self.mounting_point = ecs.MountPoint(
            container_path = '/shared-dags',
            read_only = False,
            source_volume = self.shared_volume.name
        )

        self.external_task_mounting_point = ecs.MountPoint(
            container_path = '/shared-volume',
            read_only = False,
            source_volume = self.shared_external_task_volume.name
        )

        cdk.CfnOutput(self, 'EfsFileSystemId',
            value = shared_fs.file_system_id,
            description = "EFS File System ID"
        )
        cdk.CfnOutput(self, 'EfsAccessPointId',
            value = access_point.access_point_id,
            description = "EFS Access Point ID"
        )
        cdk.CfnOutput(self, 'EfsExternalAccessPointId',
            value = external_task_access_point.access_point_id,
            description = "EFS Access Point ID"
        )