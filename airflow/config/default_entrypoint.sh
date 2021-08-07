#!/usr/bin/env bash
AIRFLOW_COMMAND="${1:-}"

# Slightly adapated from
#  https://github.com/apache/airflow/blob/v2-1-stable/scripts/in_container/prod/entrypoint_prod.sh

# See https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -euo pipefail

function run_check_with_retries {
    local cmd
    cmd="${1}"
    local countdown
    countdown="${CONNECTION_CHECK_MAX_COUNT}"

    while true
    do
        set +e
        local last_check_result
        local res
        last_check_result=$(eval "${cmd} 2>&1")
        res=$?
        set -e
        if [[ ${res} == 0 ]]; then
            echo
            break
        else
            echo -n "."
            countdown=$((countdown-1))
        fi
        if [[ ${countdown} == 0 ]]; then
            echo
            echo "ERROR! Maximum number of retries (${CONNECTION_CHECK_MAX_COUNT}) reached."
            echo
            echo "Last check result:"
            echo "$ ${cmd}"
            echo "${last_check_result}"
            echo
            exit 1
        else
            sleep "${CONNECTION_CHECK_SLEEP_TIME}"
        fi
    done
}

function run_nc() {
    # Checks if it is possible to connect to the host using netcat.
    #
    # We want to avoid misleading messages and perform only forward lookup of the service IP address.
    # Netcat when run without -n performs both forward and reverse lookup and fails if the reverse
    # lookup name does not match the original name even if the host is reachable via IP. This happens
    # randomly with docker-compose in GitHub Actions.
    # Since we are not using reverse lookup elsewhere, we can perform forward lookup in python
    # And use the IP in NC and add '-n' switch to disable any DNS use.
    # Even if this message might be harmless, it might hide the real reason for the problem
    # Which is the long time needed to start some services, seeing this message might be totally misleading
    # when you try to analyse the problem, that's why it's best to avoid it,
    local host="${1}"
    local port="${2}"
    local ip
    ip=$(python -c "import socket; print(socket.gethostbyname('${host}'))")
    nc -zvvn "${ip}" "${port}"
}

function wait_for_connection {
    # Waits for Connection to the backend specified via URL passed as first parameter
    # Detects backend type depending on the URL schema and assigns
    # default port numbers if not specified in the URL.
    # Then it loops until connection to the host/port specified can be established
    # It tries `CONNECTION_CHECK_MAX_COUNT` times and sleeps `CONNECTION_CHECK_SLEEP_TIME` between checks
    local connection_url
    connection_url="${1}"
    local detected_backend=""
    local detected_host=""
    local detected_port=""

    # Auto-detect DB parameters
    # Examples:
    #  postgres://YourUserName:password@YourHostname:5432/YourDatabaseName
    #  postgres://YourUserName:password@YourHostname:5432/YourDatabaseName
    #  postgres://YourUserName:@YourHostname:/YourDatabaseName
    #  postgres://YourUserName@YourHostname/YourDatabaseName
    [[ ${connection_url} =~ ([^:]*)://([^:@]*):?([^@]*)@?([^/:]*):?([0-9]*)/([^\?]*)\??(.*) ]] && \
        detected_backend=${BASH_REMATCH[1]} &&
        # Not used USER match
        # Not used PASSWORD match
        detected_host=${BASH_REMATCH[4]} &&
        detected_port=${BASH_REMATCH[5]} &&
        # Not used SCHEMA match
        # Not used PARAMS match

    echo BACKEND="${BACKEND:=${detected_backend}}"
    readonly BACKEND

    if [[ -z "${detected_port=}" ]]; then
        if [[ ${BACKEND} == "postgres"* ]]; then
            detected_port=5432
        elif [[ ${BACKEND} == "mysql"* ]]; then
            detected_port=3306
        elif [[ ${BACKEND} == "redis"* ]]; then
            detected_port=6379
        elif [[ ${BACKEND} == "amqp"* ]]; then
            detected_port=5672
        fi
    fi

    detected_host=${detected_host:="localhost"}

    # Allow the DB parameters to be overridden by environment variable
    echo DB_HOST="${DB_HOST:=${detected_host}}"
    readonly DB_HOST

    echo DB_PORT="${DB_PORT:=${detected_port}}"
    readonly DB_PORT
    run_check_with_retries "run_nc ${DB_HOST@Q} ${DB_PORT@Q}"
}

function create_www_user() {
    local local_password=""
    # Warning: command environment variables (*_CMD) have priority over usual configuration variables
    # for configuration parameters that require sensitive information. This is the case for the SQL database
    # and the broker backend in this entrypoint script.
    if [[ -n "${_AIRFLOW_WWW_USER_PASSWORD_CMD=}" ]]; then
        local_password=$(eval "${_AIRFLOW_WWW_USER_PASSWORD_CMD}")
        unset _AIRFLOW_WWW_USER_PASSWORD_CMD
    elif [[ -n "${_AIRFLOW_WWW_USER_PASSWORD=}" ]]; then
        local_password="${_AIRFLOW_WWW_USER_PASSWORD}"
        unset _AIRFLOW_WWW_USER_PASSWORD
    fi
    if [[ -z ${local_password} ]]; then
        echo
        echo "ERROR! Airflow Admin password not set via _AIRFLOW_WWW_USER_PASSWORD or _AIRFLOW_WWW_USER_PASSWORD_CMD variables!"
        echo
        exit 1
    fi

    airflow users create \
       --username "${_AIRFLOW_WWW_USER_USERNAME="admin"}" \
       --firstname "${_AIRFLOW_WWW_USER_FIRSTNAME="Brett"}" \
       --lastname "${_AIRFLOW_WWW_USER_LASTNME="Shinnebarger"}" \
       --email "${_AIRFLOW_WWW_USER_EMAIL="brett@somewhere.com"}" \
       --role "${_AIRFLOW_WWW_USER_ROLE="Admin"}" \
       --password "${local_password}" || true
}

function create_system_user_if_missing() {
    # This is needed in case of OpenShift-compatible container execution. In case of OpenShift random
    # User id is used when starting the image, however group 0 is kept as the user group. Our production
    # Image is OpenShift compatible, so all permissions on all folders are set so that 0 group can exercise
    # the same privileges as the default "airflow" user, this code checks if the user is already
    # present in /etc/passwd and will create the system user dynamically, including setting its
    # HOME directory to the /home/airflow so that (for example) the ${HOME}/.local folder where airflow is
    # Installed can be automatically added to PYTHONPATH
    if ! whoami &> /dev/null; then
      if [[ -w /etc/passwd ]]; then
        echo "${USER_NAME:-default}:x:$(id -u):0:${USER_NAME:-default} user:${AIRFLOW_USER_HOME_DIR}:/sbin/nologin" \
            >> /etc/passwd
      fi
      export HOME="${AIRFLOW_USER_HOME_DIR}"
    fi
}

function set_pythonpath_for_root_user() {
    # Airflow is installed as a local user application which means that if the container is running as root
    # the application is not available. because Python then only load system-wide applications.
    # Now also adds applications installed as local user "airflow".
    if [[ $UID == "0" ]]; then
        local python_major_minor
        python_major_minor="$(python --version | cut -d " " -f 2 | cut -d "." -f 1-2)"
        export PYTHONPATH="${AIRFLOW_USER_HOME_DIR}/.local/lib/python${python_major_minor}/site-packages:${PYTHONPATH:-}"
        >&2 echo "The container is run as root user. For security, consider using a regular user account."
    fi
}

function wait_for_airflow_db() {
    # Check if Airflow has a command to check the connection to the database.
    if ! airflow db check --help >/dev/null 2>&1; then
        run_check_with_retries "airflow db check"
    else
        # Verify connections to the Airflow DB by guessing the database address based on environment variables,
        # then uses netcat to check that the host is reachable.
        # This is only used by Airflow 1.10+ as there are no built-in commands to check the db connection.
        local connection_url
        if [[ -n "${AIRFLOW__CORE__SQL_ALCHEMY_CONN_CMD=}" ]]; then
            connection_url="$(eval "${AIRFLOW__CORE__SQL_ALCHEMY_CONN_CMD}")"
        else
            # if no DB configured - use sqlite db by default
            connection_url="${AIRFLOW__CORE__SQL_ALCHEMY_CONN:="sqlite:///${AIRFLOW_HOME}/airflow.db"}"
        fi
        # SQLite doesn't require a remote connection, so we don't have to wait.
        if [[ ${connection_url} != sqlite* ]]; then
            wait_for_connection "${connection_url}"
        fi
    fi
}

function wait_for_celery_backend() {
    # Verifies connection to Celery Broker
    if [[ -n "${AIRFLOW__CELERY__BROKER_URL_CMD=}" ]]; then
        wait_for_connection "$(eval "${AIRFLOW__CELERY__BROKER_URL_CMD}")"
    else
        AIRFLOW__CELERY__BROKER_URL=${AIRFLOW__CELERY__BROKER_URL:=}
        if [[ -n ${AIRFLOW__CELERY__BROKER_URL=} ]]; then
            wait_for_connection "${AIRFLOW__CELERY__BROKER_URL}"
        fi
    fi
}

function exec_to_bash_or_python_command_if_specified() {
    # If one of the commands: 'airflow', 'bash', 'python' is used, either run appropriate
    # command with exec or update the command line parameters
    if [[ ${AIRFLOW_COMMAND} == "bash" ]]; then
       shift
       exec "/bin/bash" "${@}"
    elif [[ ${AIRFLOW_COMMAND} == "python" ]]; then
       shift
       exec "python" "${@}"
    fi
}

function check_uid_gid() {
    if [[ $(id -g) == "0" ]]; then
        return
    fi
    if [[ $(id -u) == "50000" ]]; then
        >&2 echo
        >&2 echo "WARNING! You should run the image with GID (Group ID) set to 0"
        >&2 echo "         even if you use 'airflow' user (UID=50000)"
        >&2 echo
        >&2 echo " You started the image with UID=$(id -u) and GID=$(id -g)"
        >&2 echo
        >&2 echo " This is to make sure you can run the image with an arbitrary UID in the future."
        >&2 echo
        >&2 echo " See more about it in the Airflow's docker image documentation"
        >&2 echo "     http://airflow.apache.org/docs/docker-stack/entrypoint"
        >&2 echo
        # We still allow the image to run with `airflow` user.
        return
    else
        >&2 echo
        >&2 echo "ERROR! You should run the image with GID=0"
        >&2 echo
        >&2 echo " You started the image with UID=$(id -u) and GID=$(id -g)"
        >&2 echo
        >&2 echo "The image should always be run with GID (Group ID) set to 0 regardless of the UID used."
        >&2 echo " This is to make sure you can run the image with an arbitrary UID."
        >&2 echo
        >&2 echo " See more about it in the Airflow's docker image documentation"
        >&2 echo "     http://airflow.apache.org/docs/docker-stack/entrypoint"
        # This will not work so we fail hard
        exit 1
    fi
}

# Used by AIRFLOW__CORE__SQL_ALCHEMY_CONN_CMD to get the backend URI
#   so it will not be visible in the ECS task/container defs via the console
function get_db_uri_from_secret {
    local AIRFLOW_DB_CREDS=$(aws secretsmanager get-secret-value --secret-id $RDS_SECRET_ARN --output json | jq '.SecretString|fromjson')

    local MYSQL_HOST=$(echo $AIRFLOW_DB_CREDS | jq -r '.host')
    local MYSQL_USER=$(echo $AIRFLOW_DB_CREDS | jq -r '.username')
    local MYSQL_PWD=$(echo $AIRFLOW_DB_CREDS | jq -r '.password')
    local MYSQL_DBNAME=$(echo $AIRFLOW_DB_CREDS | jq -r '.dbname')
    local MYSQL_PORT=$(echo $AIRFLOW_DB_CREDS | jq -r '.port')

    local MYSQL_URI="mysql+mysqldb://$MYSQL_USER:$MYSQL_PWD@$MYSQL_HOST:$MYSQL_PORT/$MYSQL_DBNAME"
    echo $MYSQL_URI
}

# Used by AIRFLOW__CELERY__RESULT_BACKEND_CMD to get the backend URI
#   so it will not be visible in the ECS task/container defs via the console
function get_celery_result_backend_uri {
    local MYSQL_URI=$(get_db_uri_from_secret)
    echo "db+$MYSQL_URI"
}

# In Airflow image we are setting PIP_USER variable to true, in order to install all the packages
# by default with the ``--user`` flag. However this is a problem if a virtualenv is created later
# which happens in PythonVirtualenvOperator. We are unsetting this variable here, so that it is
# not set when PIP is run by Airflow later on
unset PIP_USER

check_uid_gid

# Set umask to 0002 to make all the directories created by the current user group-writeable
# This allows the same directories to be writeable for any arbitrary user the image will be
# run with, when the directory is created on a mounted volume and when that volume is later
# reused with a different UID (but with GID=0)
umask 0002

CONNECTION_CHECK_MAX_COUNT=${CONNECTION_CHECK_MAX_COUNT:=5}
readonly CONNECTION_CHECK_MAX_COUNT

CONNECTION_CHECK_SLEEP_TIME=${CONNECTION_CHECK_SLEEP_TIME:=3}
readonly CONNECTION_CHECK_SLEEP_TIME

create_system_user_if_missing
set_pythonpath_for_root_user
# Get backend conn URIs using secrets
AIRFLOW__CORE__SQL_ALCHEMY_CONN=$(get_db_uri_from_secret)
AIRFLOW__CELERY__RESULT_BACKEND=$(get_celery_result_backend_uri)
export \
  AIRFLOW__CORE__SQL_ALCHEMY_CONN \
  AIRFLOW__CELERY__RESULT_BACKEND

# create_system_user_if_missing
# set_pythonpath_for_root_user
if [[ "${CONNECTION_CHECK_MAX_COUNT}" -gt "0" ]]; then
    wait_for_airflow_db
fi

# Fargate Airflow new things
DETECTED_HOSTNAME=$(hostname)
echo -e "\n\nDETECTED_HOSTNAME=$DETECTED_HOSTNAME\n\n"
echo -e "\n\nAirflow Home: ${AIRFLOW_HOME}\n\n"
echo -e "\n\nAWS Default Region: $AWS_DEFAULT_REGION"
# Show airlfow uid/gid info
echo -e "\n\nUser Info"
id

# if [[ -n "${_PIP_ADDITIONAL_REQUIREMENTS=}" ]] ; then
#     >&2 echo
#     >&2 echo "!!!!!  Installing additional requirements: '${_PIP_ADDITIONAL_REQUIREMENTS}' !!!!!!!!!!!!"
#     >&2 echo
#     >&2 echo "WARNING: This is a developpment/test feature only. NEVER use it in production!"
#     >&2 echo "         Instead, build a custom image as described in"
#     >&2 echo
#     >&2 echo "         https://airflow.apache.org/docs/docker-stack/build.html"
#     >&2 echo
#     >&2 echo "         Adding requirements at container startup is fragile and is done every time"
#     >&2 echo "         the container starts, so it is onlny useful for testing and trying out"
#     >&2 echo "         of adding dependencies."
#     >&2 echo
#     pip install --no-cache-dir --user ${_PIP_ADDITIONAL_REQUIREMENTS}
# fi

# The `bash` and `python` commands should also verify the basic connections
# So they are run after the DB check
exec_to_bash_or_python_command_if_specified "${@}"
# Remove "airflow" if it is specified as airflow command
# This way both command types work the same way:
#
#     docker run IMAGE airflow webserver
#     docker run IMAGE webserver
#
if [[ ${AIRFLOW_COMMAND} == "airflow" ]]; then
   AIRFLOW_COMMAND="${2:-}"
   shift
fi

if [[ ${AIRFLOW_COMMAND} =~ ^(webserver)$ ]] ; then
    #   It's OK to run this multiple times
    #   See: https://airflow.apache.org/docs/apache-airflow/stable/production-deployment.html#database-backend
    airflow db upgrade || true

    # Create UI user during webserver startup
    #   It's OK to run this more than once, it will just say "admin already created"
    create_www_user

    # If a private key is supplied, set that up
    if [[ ! -z ${GIT_READ_ONLY_SECRET_ARN} ]]; then
        aws secretsmanager get-secret-value --secret-id $GIT_READ_ONLY_SECRET_ARN | jq -r .SecretString | tee ${AIRFLOW_HOME}/.ssh/id_rsa > /dev/null
        chmod 400 ${AIRFLOW_HOME}/.ssh/id_rsa
        eval "$(ssh-agent -s)"
        ssh-add -k ${AIRFLOW_HOME}/.ssh/id_rsa
        ssh-keyscan github.com > ${AIRFLOW_HOME}/.ssh/known_hosts
    fi

    # Sync the repository to the shared EFS file systems
    #   This is where the DAGs will live
    echo -e "\n\nSyncing Repo"
    source /sync_repo.sh
    sync_repo
    echo "Done in webserver"
fi

# Note: the broker backend configuration concerns only a subset of Airflow components
if [[ ${AIRFLOW_COMMAND} =~ ^(scheduler|celery|worker|flower)$ ]] \
    && [[ "${CONNECTION_CHECK_MAX_COUNT}" -gt "0" ]]; then
    wait_for_celery_backend
    echo "Got celery backend"
    sleep 15
fi
# echo "about to exec airflow $@"

exec "airflow" "${@}"