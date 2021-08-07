from typing import List
from dataclasses import dataclass

from aws_cdk import (
    core as cdk,
    aws_ec2 as ec2,
    aws_ecs as ecs
)
from jsii import Number

@dataclass(frozen=True)
class AutoScalingConfig:
    min_task_count: Number
    max_task_count: Number
    cpu_usage_percent: Number = None
    mem_usage_percent: Number = None

@dataclass(frozen=True)
class ContainerConfig:
    name: str
    container_port: Number
    command: List[str]
    entry_point: List[str]
    health_check: ecs.HealthCheck

@dataclass(frozen=True)
class TaskConfig:
    cpu: Number
    memory_limit_mib: Number


@dataclass(frozen=True)
class MySQLConfig:
    instance_name: str
    db_name: str
    port: Number
    master_username: str
    instance_type: ec2.InstanceType
    allocated_storage_in_gb: Number
    backup_retention_in_days: cdk.Duration


# Webserver Task and Container Configs
WEBSERVER_TASK_CONFIG = TaskConfig(
    cpu = 1024,
    memory_limit_mib = 2048
)

WEBSERVER_CONFIG = ContainerConfig(
    name = 'WebserverContainer',
    container_port = 8080,
    entry_point = ['/default_entrypoint.sh'],
    command = ['webserver'],
    health_check = None
)

FLOWER_CONFIG = ContainerConfig(
    name = 'FlowerContainer',
    container_port = 5555,
    entry_point = ['/default_entrypoint.sh'],
    command = ['celery', 'flower'],
    health_check = None
)

# Worker Task, Container and Autoscaling Configs
WORKER_TASK_CONFIG = TaskConfig(
    cpu = 1024,
    memory_limit_mib = 8192
)

WORKER_CONFIG = ContainerConfig(
    name = 'WorkerContainer',
    container_port = 8793,
    entry_point = ['/default_entrypoint.sh'],
    command = ['celery', 'worker'],
    health_check = None
)

WORKER_AUTOSCALING_CONFIG = AutoScalingConfig(
    min_task_count = 2,
    max_task_count = 4,
    cpu_usage_percent = 70,
    mem_usage_percent = 70
)

# Redis Task and Container configs
REDIS_TASK_CONFIG = TaskConfig(
    cpu = 512,
    memory_limit_mib = 1024
)

REDIS_CONFIG = ContainerConfig(
    name = 'RedisContainer',
    container_port = 6379,
    entry_point = None,
    command = None,
    health_check = ecs.HealthCheck(
                    command = ["CMD", "redis-cli", "ping"],
                    interval = cdk.Duration.seconds(10),
                    timeout = cdk.Duration.seconds(30),
                    retries = 5,
                    start_period = cdk.Duration.seconds(30)
                )
)

# Scheduler Task and Container configs
SCHEDULER_TASK_CONFIG = TaskConfig(
    cpu = 1024,
    memory_limit_mib = 2048
)

SCHEDULER_CONFIG = ContainerConfig(
    name = 'SchedulerContainer',
    container_port = 8081,
    entry_point = ['/default_entrypoint.sh'],
    command = ['scheduler'],
    health_check = ecs.HealthCheck(
                    command = ['CMD-SHELL', 'airflow jobs check --job-type SchedulerJob --hostname "$(hostname)"'],
                    interval = cdk.Duration.seconds(15),
                    timeout = cdk.Duration.seconds(10),
                    retries = 5,
                    start_period = cdk.Duration.seconds(30),
                )
)

DEFAULT_DB_CONFIG = MySQLConfig(
    instance_name = 'fargate-airflow',
    db_name = 'airflow',
    port = 3306,
    master_username = 'airflow',
    # Micro doesn't support encryption at rest
    instance_type = ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE2,
                                        ec2.InstanceSize.SMALL),
    # 20 is minimum
    allocated_storage_in_gb = 20,
    backup_retention_in_days = cdk.Duration.days(7)
)