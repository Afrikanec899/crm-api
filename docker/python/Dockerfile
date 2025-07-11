FROM python:3.8-alpine

ENV PYTHONUNBUFFERED 1

RUN apk update \
  # psycopg2 dependencies
  && apk add --no-cache --virtual build-deps gcc python3-dev libressl-dev musl-dev git build-base openssl-dev cargo libffi-dev py-cffi \
  && apk add --no-cache postgresql-dev tesseract-ocr \
  # Pillow dependencies
  && apk add --no-cache ca-certificates jpeg-dev zlib-dev freetype-dev giflib-dev lcms2-dev openjpeg-dev libpng-dev tiff-dev tk-dev tcl-dev \
  # Translations dependencies
  && apk add --no-cache gettext libxml2-dev libxslt-dev

RUN addgroup -S crm-api \
    && adduser -S -G crm-api crm-api

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements
RUN python3 -m pip install -U pip
RUN pip install -r /requirements/base.txt \
    && rm -rf /requirements