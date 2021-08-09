import os
from aws_cdk import (
    core as cdk,
    aws_ecs as ecs,
    aws_s3 as s3,
    aws_logs as logs,
    aws_ecr_assets as ecr_assets
)
from fairflow.constructs.efs_construct import EfsConstruct
from fairflow.constructs.rds_construct import RDSConstruct
from fairflow.constructs.secrets_construct import SecretsConstruct
from fairflow.constructs.redis_construct import RedisConstruct
from fairflow.constructs.dag_tasks import ExternalDagTasks
from fairflow.constructs.policies import PolicyConstruct
from fairflow.constructs.webserver_construct import WebserverConstruct
from fairflow.constructs.worker_construct import WorkerConstruct
from fairflow.constructs.scheduler_construct import SchedulerConstruct

from fairflow.constructs.contruct_properties import (
    FairflowConstructProps,
    FairflowChildConstructProps,
    RedisConstructProps
)

class FairflowConstruct(cdk.Construct):
    def __init__(self, scope: cdk.Construct, id: str, props: FairflowConstructProps):
        super().__init__(scope, id)

        # Used for Airflow Worker logs
        #   see: https://airflow.apache.org/docs/apache-airflow/stable/production-deployment.html#logging
        s3_logs_bucket = s3.Bucket(self, 'FairflowWorkerLogsS3Bucket',
            # comment these two lines out and uncomment retain if you want to
            #   retain the worker logs
            auto_delete_objects = True,
            removal_policy = cdk.RemovalPolicy.DESTROY,
            # removal_policy = cdk.RemovalPolicy.RETAIN
        )
        cdk.CfnOutput(self, 'FairflowWorkerLogsS3BucketName',
            value = s3_logs_bucket.bucket_name,
            description = "S3 Bucket where Worker execution logs will go"
        )

        # Create a shared EFS (so Webserver, Scheduler and Worker are looking at synchronized DAGs)
        #       see: https://airflow.apache.org/docs/apache-airflow/stable/production-deployment.html#multi-node-cluster
        #            about synchronizing DAGs
        efs_construct = EfsConstruct(self, 'FairflowEFSConstruct', vpc_props = props.vpc_props)
        # Create the airflow meta database (or cluster if highly available)
        #       see: https://airflow.apache.org/docs/apache-airflow/stable/concepts/scheduler.html#database-requirements
        #            about High Availability requirements
        rds_construct = RDSConstruct(self, 'FairflowRdsMySQL8',
            vpc_props = props.vpc_props,
            highly_available = props.highly_available
        )
        # Manually created secrets
        #       see: https://docs.aws.amazon.com/cdk/api/latest/docs/aws-secretsmanager-readme.html
        #            about why we need to manually create some secrets outside CDK and import them
        secrets_construct = SecretsConstruct(self, 'SecretsConstruct')

        # Cloudwatch logging driver for the containers (separate from s3 logging for Worker logs)
        cloudwatch_logging = ecs.AwsLogDriver(
            stream_prefix = 'Fairflow',
            log_retention =  logs.RetentionDays.ONE_MONTH
        )

        # Redis (Job Queue Broker).  We'll either use a Fargate service or AWS Elasticache
        #   depending on the highly available flag
        redis_construct = RedisConstruct(self, 'RedisConstruct',
                RedisConstructProps(
                    vpc_props = props.vpc_props,
                    cluster = props.cluster,
                    logging = cloudwatch_logging,
                    highly_available = props.highly_available
                )
            )

        # see: https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html
        #   we only need to worry about env vars we want to explictily override from the defaults
        ENV_VAR = {
            'AIRFLOW__CORE__EXECUTOR': 'CeleryExecutor',
            # 'AIRFLOW__CORE__SQL_ALCHEMY_CONN': '', # Set in webserver_entry.sh
            #  see: https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html#sql-engine-collation-for-ids
            'AIRFLOW__CORE__SQL_ENGINE_COLLATION_FOR_IDS': 'utf8mb3_general_ci',
            'AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION': 'true',
            #  This will likely need to be adjusted for specific use cases
            #  e.g. if we can autoscale to 4 workers and each worker can have 4 tasks max, then 16 is good
            #       if we are using a small worker and farming tasks externally via ECS Operator, it could be much higher
            'AIRFLOW__CORE__PARALLELISM': '16',
            #  Overridable in DAGs.  Max tasks allowed to run concurrently within a DAG
            'AIRFLOW__CORE__DAG_CONCURRENCY': '4',
            #  Overridable in DAGs.  Can multiple of a DAG run at the same time
            'AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG': '1',
            # Default is {AIRFLOW_HOME}/dags, but we want to use EFS for synchronizing DAGs
            'AIRFLOW__CORE__LOAD_DEFAULT_CONNECTIONS': 'false',
            'AIRFLOW__CORE__DAGS_FOLDER': efs_construct.mounting_point.container_path,
            'AIRFLOW__CORE__LOAD_EXAMPLES': 'true',
            # 'AIRFLOW__CELERY__BROKER_URL': 'sqs://',
            # 'AIRFLOW__CELERY__BROKER_URL': f'redis://:@{redis_construct.redis_host}:6379/0',
            'AIRFLOW__CELERY__BROKER_URL': f'redis://:@{redis_construct.redis_host}:6379/0',

            # 'AIRFLOW__CELERY__RESULT_BACKEND': '',  # Set in webserver_entry.sh
            # This should be set to the longest expected SLA of all DAGs
            'AIRFLOW__CELERY_BROKER_TRANSPORT_OPTIONS__VISIBILITY_TIMEOUT': '1800',
            # Consider the resources you expect tasks to need, the sizing of the Fargate tasks
            #   in the configs.  If you set autoscaling to a high number, you may need to adjust
            #   the PARALLELISM number above
            'AIRFLOW__CELERY__WORKER_CONCURRENCY': '4',
            'AIRFLOW__LOGGING__REMOTE_LOGGING': 'true',
            'AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER': f's3://{s3_logs_bucket.bucket_name}/logs',
            'AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID': 'aws_default',
            'AIRFLOW__LOGGING__ENCRYPT_S3_LOGS': 'false',
            'AIRFLOW__API__AUTH_BACKEND': 'airflow.api.auth.backend.basic_auth',
            'AIRFLOW__SCHEDULER__CATCHUP_BY_DEFAULT': 'false',
            'AIRFLOW__WEBSERVER__DAG_DEFAULT_VIEW': 'graph',
            # *********
            # Additional Env Vars
            # *********
            # connections defined in env vars are not visible in the UI -> Admin -> Connections
            #   but they are there and will work. You can explicitly create them in the
            #   entrypoint if you want with the Airflow CLI
            #   aws:// means just use the default (i.e. the task execution role privledges)
            #   see: https://airflow.apache.org/docs/apache-airflow/stable/howto/connection.html#storing-a-connection-in-environment-variables
            'AIRFLOW_CONN_AWS_DEFAULT': 'aws://',
            # Used by default aws connection / boto3
            'AWS_DEFAULT_REGION': props.vpc_props.vpc.env.region,
            'DAG_REPOSITORY': os.getenv('DAG_REPOSITORY'),
            # If your repo needs SSH access, keep it in secrets and supply the key
            #   see: https://docs.github.com/en/developers/overview/managing-deploy-keys#deploy-keys
            'GIT_READ_ONLY_SECRET_ARN': os.getenv('GIT_READ_ONLY_SECRET_ARN', ''),
            # REDIS_HOST is defined via Cloud Map Service Discovery config when not
            #   highly available, or else is the primary endpoint of the aws elasticache
            #   deployment
            'REDIS_HOST': redis_construct.redis_host,
            # RDS Auto-Generated Secret ARN, used by the default_entrypoint to construct
            #    the AIRFLOW__CORE__SQL_ALCHEMY_CONN without exposing the secret to the
            #    ECS container console
            'RDS_SECRET_ARN': rds_construct.backend_secret.secret_arn,
            # These are used when we use the ECS Operator Type to say where
            #   to launch on-demand tasks
            'CLUSTER': props.cluster.cluster_name,
            'SECURITY_GROUP': props.vpc_props.default_vpc_security_group.security_group_id,
            'SUBNETS': ','.join(subnet.subnet_id for subnet in props.vpc_props.vpc.private_subnets)
        }

        # Using secret env vars so they can't be seen in the ECS console task definittions -> containers
        SECRET_ENV_VAR = {
            'AIRFLOW__CORE__FERNET_KEY': secrets_construct.fernet_secret,
            '_AIRFLOW_WWW_USER_PASSWORD': secrets_construct.admin_password,
            # credentials for accessing flower at {AlbDNS}:5555
            'AIRFLOW__CELERY__FLOWER_BASIC_AUTH': secrets_construct.flower_credentials
        }

        # Build Airflow Docker Image from Dockerfile
        airflow_image_asset = ecr_assets.DockerImageAsset(self, 'AirflowBuildImage',
            directory = './airflow'
        )

        # Create Task Definitions for on-demand Fargate tasks, invoked via ECS Operators
        external_dag_tasks = ExternalDagTasks(self, 'ExternalDagTasksConstruct',
            shared_volume = efs_construct.shared_external_task_volume,
            mounting_point = efs_construct.external_task_mounting_point
        )

        # Policies to use
        policies = PolicyConstruct(self, 'FairflowTaskPolicies',
            efs_arn = efs_construct.file_system_arn,
            s3_logs_bucket_arn = s3_logs_bucket.bucket_arn,
            rds_secret_arn = rds_construct.backend_secret.secret_arn,
            cluster_arn = props.cluster.cluster_arn,
            external_task_arns = external_dag_tasks.get_external_task_arns(),
            external_tasks_log_group_arn = \
                external_dag_tasks.container_logging.log_group.log_group_arn
        )

        # Common args for child constructs
        child_props = FairflowChildConstructProps(
            vpc_props = props.vpc_props,
            cluster = props.cluster,
            env_vars = ENV_VAR,
            secret_env_vars = SECRET_ENV_VAR,
            logging = cloudwatch_logging,
            airflow_image = airflow_image_asset,
            shared_volume = efs_construct.shared_volume,
            mounting_point = efs_construct.mounting_point,
            policies = policies,
            highly_available = props.highly_available,
            enable_autoscaling = props.enable_autoscaling
        )

        # Adding an explicit dependency so these wait until the DB backend is ready
        webserver_construct = WebserverConstruct(self, 'WebserverConstruct', child_props)
        webserver_construct.webserver_service.node.add_dependency(rds_construct.rds_instance)

        # The webserver handles db initialization and DAG repo syncing, so wait for that to boot up
        #   these also depend on redis so wait for that to pop up too
        scheduler_construct = SchedulerConstruct(self, 'SchedulerConstruct', child_props)
        scheduler_construct.scheduler_service.node.add_dependency(
            webserver_construct.webserver_service)
        scheduler_construct.scheduler_service.node.add_dependency(
            redis_construct.dynamic_dependency)

        worker_construct = WorkerConstruct(self, 'WorkerConstruct', child_props)
        worker_construct.worker_service.node.add_dependency(
            webserver_construct.webserver_service)
        worker_construct.worker_service.node.add_dependency(
            redis_construct.dynamic_dependency)

