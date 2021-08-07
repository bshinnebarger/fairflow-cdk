import json

from aws_cdk import (
    core as cdk,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as secrets
)

from fairflow.config import DEFAULT_DB_CONFIG
from fairflow.constructs.contruct_properties import VpcProps

class RDSConstruct(cdk.Construct):

    def __init__(self, scope: cdk.Construct, id: str,
                       vpc_props: VpcProps, highly_available: bool):
        super().__init__(scope, id)

        self.backend_secret = secrets.Secret(self, 'DBSecret',
            description = 'airflow RDS secrets',
            generate_secret_string = \
                secrets.SecretStringGenerator(
                    secret_string_template = json.dumps({
                        'username': DEFAULT_DB_CONFIG.master_username
                    }),
                    generate_string_key = 'password',
                    exclude_uppercase = False,
                    require_each_included_type = False,
                    include_space = False,
                    exclude_punctuation = True,
                    exclude_lowercase = False,
                    exclude_numbers = False,
                    password_length = 16
                )
        )

        # We need to use MySQL 8+ (or Postgres 9.6+) to take advantage of Airflow 2's
        #   Scheduler high availability feature.  If the highly_available bool is True
        #   we'll enable Multi-AZ which will create a read-only replica for failover.
        #   see: https://airflow.apache.org/docs/apache-airflow/stable/concepts/scheduler.html#database-requirements
        self.rds_instance = rds.DatabaseInstance(self, 'RDSInstance',
            instance_identifier = DEFAULT_DB_CONFIG.instance_name,
            database_name = DEFAULT_DB_CONFIG.db_name,
            credentials = rds.Credentials.from_secret(self.backend_secret),
            engine = rds.DatabaseInstanceEngine.mysql(
                version = rds.MysqlEngineVersion.VER_8_0_25
            ),
            vpc = vpc_props.vpc,
            publicly_accessible = False,
            vpc_subnets = ec2.SubnetSelection(subnets=vpc_props.vpc.private_subnets),
            security_groups = [vpc_props.default_vpc_security_group],
            port = DEFAULT_DB_CONFIG.port,
            instance_type = DEFAULT_DB_CONFIG.instance_type,
            allocated_storage = DEFAULT_DB_CONFIG.allocated_storage_in_gb,
            storage_type= rds.StorageType.GP2,
            storage_encrypted = True,
            multi_az = highly_available,
            delete_automated_backups = True,
            auto_minor_version_upgrade = False,
            backup_retention = DEFAULT_DB_CONFIG.backup_retention_in_days,
            deletion_protection = False
        )

        self.rds_instance.connections.allow_default_port_from(
            other = vpc_props.default_vpc_security_group,
            description = 'RDS Ingress'
        )

        cdk.CfnOutput(self, 'MySQL Endpoint',
            value = self.rds_instance.db_instance_endpoint_address,
            description = "MySQL Endpoint"
        )
