from dataclasses import dataclass
from typing import Mapping

from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_secretsmanager as secrets,
)
from jsii import Number
from fairflow.constructs.policies import PolicyConstruct


@dataclass(frozen=True)
class VpcProps:
    vpc: ec2.IVpc
    default_vpc_security_group: ec2.ISecurityGroup


@dataclass(frozen=True)
class FairflowConstructProps:
    vpc_props: VpcProps
    cluster: ecs.ICluster
    highly_available: bool
    enable_autoscaling: bool


@dataclass(frozen=True)
class FairflowChildConstructProps:
    vpc_props: VpcProps
    cluster: ecs.ICluster
    env_vars: Mapping[str, str]
    secret_env_vars: Mapping[str, secrets.Secret]
    logging: ecs.AwsLogDriver
    airflow_image: ecr_assets.DockerImageAsset
    shared_volume: ecs.Volume
    mounting_point: ecs.MountPoint
    policies: PolicyConstruct
    highly_available: bool
    enable_autoscaling: bool


@dataclass(frozen=True)
class RedisConstructProps:
    vpc_props: VpcProps
    cluster: ecs.ICluster
    logging: ecs.AwsLogDriver
    highly_available: bool


# External Fargate Tasks invoked by ECS Operator
@dataclass(frozen=True)
class ContainerInfo:
    name: str
    asset_dir: str


@dataclass(frozen=True)
class ExternalTaskProps:
    task_family_name: str
    container_info: ContainerInfo
    cpu: Number
    memory_limit_mib: Number
    logging: ecs.LogDriver
    shared_volume: ecs.Volume
    mounting_point: ecs.MountPoint