from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_servicediscovery as sdiscovery,
    aws_elasticache as ecache
)

from fairflow.config import (
    REDIS_CONFIG,
    REDIS_TASK_CONFIG
)
from fairflow.constructs.contruct_properties import RedisConstructProps

class RedisConstruct(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str, props: RedisConstructProps):
        super().__init__(scope, id)

        if props.highly_available:
            self.redis_host = self.setup_aws_elasticache_redis(props)
            self.dynamic_dependency = self.redis_replication_group
        else:
            self.redis_host = self.setup_fargate_redis_service(props)
            self.dynamic_dependency = self.redis_service

        props.vpc_props.default_vpc_security_group.connections.allow_from(
            other = props.vpc_props.default_vpc_security_group,
            port_range = ec2.Port.tcp(6379)
        )


    def setup_aws_elasticache_redis(self, props: RedisConstructProps) -> str:

        redis_subnet_group = ecache.CfnSubnetGroup(self, 'RedisElasticacheSubnetGroup',
            description = 'Redis Elasticache Subnet Group',
            subnet_ids = [subnet.subnet_id for subnet in props.vpc_props.vpc.private_subnets],
            cache_subnet_group_name = 'redis-elasticache-subnet-group'
        )

        # Celery does not support Redis clusters, so it's important to set
        #   the cache_parameter_group_name as below (excluding .cluster.on)
        #   node groups has to be one in a non-cluster environment as well
        #   Essentially we're creating a normal deployment and a read-only replica
        #   in another AZ for failover
        #   see: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-elasticache-replicationgroup.html
        self.redis_replication_group = ecache.CfnReplicationGroup(self, 'RedisReplicationGroup',
            engine = 'redis',
            engine_version = '6.x',
            cache_parameter_group_name = 'default.redis6.x',
            num_node_groups = 1,
            replicas_per_node_group = 1,
            automatic_failover_enabled = True,
            auto_minor_version_upgrade = False,
            cache_node_type = 'cache.t3.micro',
            port = REDIS_CONFIG.container_port,
            multi_az_enabled = True,
            security_group_ids = [props.vpc_props.default_vpc_security_group.security_group_id],
            snapshot_retention_limit = 0,
            cache_subnet_group_name=redis_subnet_group.cache_subnet_group_name,
            replication_group_description = 'Redis Cluster Replication Group'
        )
        self.redis_replication_group.add_depends_on(redis_subnet_group)

        return self.redis_replication_group.attr_primary_end_point_address


    def setup_fargate_redis_service(self, props: RedisConstructProps) -> str:
        redis_task = ecs.FargateTaskDefinition(self, 'RedisTask',
            cpu = REDIS_TASK_CONFIG.cpu,
            memory_limit_mib = REDIS_TASK_CONFIG.memory_limit_mib
        )

        # redis has no environment, secrets, entrypoint or command
        #   it's also using standard registry docker pull, not the airflow
        #   image the other services use
        redis_container = redis_task.add_container(REDIS_CONFIG.name,
            container_name = REDIS_CONFIG.name,
            image = ecs.ContainerImage.from_registry(name = 'redis:6.2.5'),
            logging = props.logging,
            health_check = REDIS_CONFIG.health_check
        )
        redis_container.add_port_mappings(ecs.PortMapping(
            container_port = REDIS_CONFIG.container_port
        ))

        self.redis_service = ecs.FargateService(self, 'RedisService',
            cluster = props.cluster,
            task_definition = redis_task,
            security_group = props.vpc_props.default_vpc_security_group,
            platform_version = ecs.FargatePlatformVersion.VERSION1_4,
            desired_count = 1
        )

        # Add this service to a private dns namespace via Cloud Map
        #   to enable service discovery (i.e. be able to reference redis from
        #   the worker and flower services via the REDIS_HOST environment variable
        #   pointing to {service_name}.{namespace}, redis.fairflow)
        service = self.redis_service.enable_cloud_map(
            cloud_map_namespace = sdiscovery.PrivateDnsNamespace(self, 'PrivateNamespace',
                vpc = props.vpc_props.vpc,
                name = 'fairflow'
            ),
            name = 'redis'
        )

        return f'{service.service_name}.{service.namespace.namespace_name}'