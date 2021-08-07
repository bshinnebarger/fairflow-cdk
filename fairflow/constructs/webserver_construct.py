import os
from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elb
)

from fairflow.constructs.contruct_properties import FairflowChildConstructProps
from fairflow.config import (
    FLOWER_CONFIG,
    WEBSERVER_CONFIG,
    WEBSERVER_TASK_CONFIG
)

class WebserverConstruct(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str, props: FairflowChildConstructProps):
        super().__init__(scope, id)

        webserver_task = ecs.FargateTaskDefinition(self, 'WebserverTask',
            cpu = WEBSERVER_TASK_CONFIG.cpu,
            memory_limit_mib = WEBSERVER_TASK_CONFIG.memory_limit_mib,
            volumes = [props.shared_volume]
        )
        props.policies.attach_policies(webserver_task.task_role)

        webserver_task.add_container(WEBSERVER_CONFIG.name,
            container_name = WEBSERVER_CONFIG.name,
            image = ecs.ContainerImage.from_docker_image_asset(props.airflow_image),
            logging = props.logging,
            environment = props.env_vars,
            secrets = props.secret_env_vars,
            entry_point = WEBSERVER_CONFIG.entry_point,
            command = WEBSERVER_CONFIG.command,
            port_mappings = [ecs.PortMapping(container_port = WEBSERVER_CONFIG.container_port)]
        ).add_mount_points(props.mounting_point)

        # Flower UI is for monitoring the Redis queue broker
        webserver_task.add_container(FLOWER_CONFIG.name,
            container_name = FLOWER_CONFIG.name,
            image = ecs.ContainerImage.from_docker_image_asset(props.airflow_image),
            logging = props.logging,
            environment = {**props.env_vars},
            secrets = props.secret_env_vars,
            entry_point = FLOWER_CONFIG.entry_point,
            command = FLOWER_CONFIG.command,
            port_mappings = [ecs.PortMapping(container_port = FLOWER_CONFIG.container_port)]
        )

        # I'm not making the webserver(s) highly available, just the scheduler /
        #   celery backend.  If the AZ goes down, fargate should be able to
        #   pop another one up quickly in one of the other available AZs.
        #   If you want to enable more than one webserver
        #      see: https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html?highlight=csrf#secret-key
        self.webserver_service = ecs.FargateService(self, 'WebserverService',
            cluster = props.cluster,
            task_definition = webserver_task,
            security_group = props.vpc_props.default_vpc_security_group,
            platform_version = ecs.FargatePlatformVersion.VERSION1_4,
            desired_count = 1
        )

        self.load_balancer_dns_name = cdk.CfnOutput(self, 'FairflowAlbDnsName',
            value = self.attach_load_balancer(props.vpc_props.vpc)
        )


    def attach_load_balancer(self, vpc: ec2.IVpc) -> str:
        load_balancer = elb.ApplicationLoadBalancer(self, 'FairflowAlb',
            vpc = vpc,
            internet_facing = True
        )

        # If we supply the IP_WHITELIST environment variable, then we will restrict access
        #   to the public load balancer to those IPs
        ips = []
        if os.getenv('IP_WHITELIST'):
            ips = os.getenv('IP_WHITELIST').split(',')

        listener = load_balancer.add_listener('Listener',
            port = 80,
            open = (len(ips) == 0)
        )

        for ip in ips:
            listener.connections.allow_from(
                other = ec2.Peer.ipv4(f'{ip}/32'),
                port_range = ec2.Port.tcp(80),
                description = 'IP Security Policy'
            )

        listener.add_targets('FairflowWebserverServiceUITargetGroup',
            health_check = elb.HealthCheck(
                port = 'traffic-port',
                protocol = elb.Protocol.HTTP,
                path = '/health'
            ),
            port = 80,
            targets = [self.webserver_service], # Chooses default container
            deregistration_delay = cdk.Duration.seconds(60)
        )

        # by default when adding a service to "targets" in add_targets(), it will
        #   look at the default container (first one added, webserver), so we
        #   need to say "go to flower container"
        #   see: https://docs.aws.amazon.com/cdk/api/latest/docs/aws-ecs-readme.html#include-an-applicationnetwork-load-balancer
        flower_target = self.webserver_service.load_balancer_target(
            container_name = FLOWER_CONFIG.name,
            container_port = FLOWER_CONFIG.container_port,
        )

        flower_listener = load_balancer.add_listener('FlowerListener',
            port = 5555,
            protocol = elb.ApplicationProtocol.HTTP,
            open = (len(ips) == 0)
        )

        for ip in ips:
            flower_listener.connections.allow_from(
                other = ec2.Peer.ipv4(f'{ip}/32'),
                port_range = ec2.Port.tcp(5555),
                description = 'IP Security Policy'
            )

        flower_listener.add_targets('FairflowWebserverServiceFlowerTargetGroup',
            health_check = elb.HealthCheck(
                port = 'traffic-port',
                protocol = elb.Protocol.HTTP,
                path = '/healthcheck'
            ),
            protocol = elb.ApplicationProtocol.HTTP,
            port = 5555,
            targets = [flower_target]
        )

        return load_balancer.load_balancer_dns_name