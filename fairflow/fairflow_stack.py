from aws_cdk import (
    core as cdk,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticache as ecache
)

from fairflow.constructs.fairflow_construct import FairflowConstruct
from fairflow.constructs.contruct_properties import (
    VpcProps,
    FairflowConstructProps
)

class FairflowStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Tag everything with the name of the stack e.g. FairflowStack
        #   (should be useful for filtering billing)
        cdk.Tags.of(scope).add('Stack', construct_id)
        # Create VPC, ECS Cluster, Security Group (shared by assets)
        vpc = ec2.Vpc(self, 'FairflowVpc', max_azs=2)
        cluster = ecs.Cluster(self, 'FairflowECSCluster', vpc=vpc)
        default_vpc_security_group = ec2.SecurityGroup(self, 'FairflowSecurityGroup', vpc = vpc)

        # Create a Bastion Host so we can inspect the airflow metadb / look at EFS
        # You can comment this out if you don't want it
        ec2.BastionHostLinux(self, 'FairflowBastionHost',
            vpc = vpc,
            security_group = default_vpc_security_group,
        )

        # Create Webserver(s), Scheduler(s), Worker(s), Redis
        FairflowConstruct(self, 'FairflowConstruct',
            FairflowConstructProps(
                vpc_props = VpcProps(
                    vpc = vpc,
                    default_vpc_security_group = default_vpc_security_group
                ),
                cluster = cluster,
                highly_available = False,
                enable_autoscaling = False
            )
        )
