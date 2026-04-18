FROM --platform=linux/x86_64 sweb.env.py.x86_64.3504be719718bf557b7469:latest

ENV http_proxy=http://10.68.168.9:7892
ENV https_proxy=http://10.68.168.9:7892

COPY ./local_repo /local_repo
COPY ./local_repo /local_repo
COPY ./local_repo /local_repo
COPY ./local_repo /local_repo
COPY ./local_repo /local_repo
COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
