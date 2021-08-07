#!/usr/bin/env bash

function sync_repo {
  if [ -d "${AIRFLOW__CORE__DAGS_FOLDER}" ] ; then
    if [ "$(ls -A ${AIRFLOW__CORE__DAGS_FOLDER})" ]; then
      echo "Pulling latest master branch"
      cd ${AIRFLOW__CORE__DAGS_FOLDER}
      git pull
      cd $OLDPWD
    else
      echo "Dir empty, cloning master branch"
      git clone ${DAG_REPOSITORY} ${AIRFLOW__CORE__DAGS_FOLDER}
    fi
  else
    echo "Directory ${AIRFLOW__CORE__DAGS_FOLDER} not found"
  fi
}
