import setuptools


with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="fairflow",
    version="0.0.1",

    description="Airflow 2.0 CDK Construct",
    long_description=long_description,
    long_description_content_type="text/markdown",

    author="author",

    package_dir={"": "fairflow"},
    packages=setuptools.find_packages(where="fairflow"),

    install_requires=[
        "aws-cdk.core==1.115.0",
        "aws_cdk.aws_elasticache==1.115.0",
        "aws-cdk.aws_ec2==1.115.0",
        "aws-cdk.aws_ecs==1.115.0",
        "aws-cdk.aws_ecs_patterns==1.115.0",
        "aws-cdk.aws_ecr_assets==1.115.0",
        "aws-cdk.aws_secretsmanager==1.115.0",
        "aws_cdk.aws_rds==1.115.0",
        "cryptography==3.4.7", # for fernet key gen
    ],

    python_requires=">=3.6",

    classifiers=[
        "Development Status :: 4 - Beta",

        "Intended Audience :: Developers",

        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",

        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",

        "Typing :: Typed",
    ],
)
