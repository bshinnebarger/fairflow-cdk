import os
from typing import List

from aws_cdk import (
    core as cdk,
    aws_secretsmanager as secrets,
    aws_ecs as ecs
)

class SecretsConstruct(cdk.Construct):

    def __init__(self, scope: cdk.Construct, id: str):
        super().__init__(scope, id)

        # Make sure you manually generate these secrets prior to
        #   deploying this stack, as well as sourcing the variables in the
        #   shell, e.g. export $(xargs < ./envs/us-east-1.env)
        #   see: README

        # fernet key secret for encrypting sensitive information like connections
        #    (manually created, as this should remain static)
        self.fernet_secret = ecs.Secret.from_secrets_manager(
            secrets.Secret.from_secret_arn(self, 'FernetSecret',
                secret_arn = os.getenv('AIRFLOW_FERNET_KEY_SECRET_ARN')
            )
        )

        # airflow ui admin password (manually created)
        self.admin_password = ecs.Secret.from_secrets_manager(
            secrets.Secret.from_secret_arn(self, 'AirflowUIAdminPassword',
                secret_arn = os.getenv('AIRFLOW_ADMIN_PASSWORD_SECRET_ARN')
            )
        )

        # flower ui credentials (manually created)
        self.flower_credentials = ecs.Secret.from_secrets_manager(
            secrets.Secret.from_secret_arn(self, 'FlowerCredentials',
                secret_arn = os.getenv('AIRFLOW_FLOWER_CREDENTIALS_SECRET_ARN')
            )
        )

