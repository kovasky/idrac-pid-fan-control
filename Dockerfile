FROM python:slim-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
    ipmitool \
    openssh-client \
    sshpass

WORKDIR /app

COPY ./src/*.py /app/

ENTRYPOINT ["python3", "main.py"]