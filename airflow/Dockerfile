FROM apache/airflow:2.1.2-python3.8

# AIRFLOW_HOME should default to /opt/airflow/

USER root

# licurl4 + pycurl required by celery worker
# jq used by custom_webserver_healthcheck.sh
# git used by sync_repo.sh
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         build-essential \
         libcurl4-openssl-dev \
         libssl-dev \
         jq \
         git \
         unzip \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# used to build backend uri's via secretsmanager
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && sudo ./aws/install

RUN mkdir -p "$AIRFLOW_HOME/.ssh"
RUN mkdir -p "$AIRFLOW_HOME/logs"
RUN chown -R airflow:root ${AIRFLOW_HOME}

COPY ./config/* /
COPY ./extra_requirements.txt /
COPY ./constraints-2.1.2-python3.8.txt /

# 8080/5555 -> webserver/flower
EXPOSE 8080/tcp 5555/tcp

USER airflow

# Used by celery workers
RUN pip install --no-cache-dir pycurl
# Extra reqs
RUN pip install --no-cache-dir -r /extra_requirements.txt -c /constraints-2.1.2-python3.8.txt

WORKDIR ${AIRFLOW_HOME}


