#!/usr/bin/env python3
import os

# For consistency with TypeScript code, `cdk` is the preferred import name for
#   the CDK's core module
from aws_cdk import core as cdk
from fairflow.fairflow_stack import FairflowStack

app = cdk.App()
FairflowStack(app, "FairflowStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Specialize this stack for the AWS Account and Region that are implied
    #   by the current CLI configuration
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */
    #env=core.Environment(account='123456789012', region='us-east-1'),

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
)

app.synth()
