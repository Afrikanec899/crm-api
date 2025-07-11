FROM docker:18.09

ENV PYTHONUNBUFFERED 1

RUN apk update && apk upgrade \
   # Installing docker-compose:
  && apk add python python-dev py-pip build-base openssl-dev libffi-dev

RUN pip install docker-compose  dump-env
