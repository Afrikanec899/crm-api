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


# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements
RUN pip install --upgrade pip
RUN pip install -r /requirements/local.txt

COPY ./docker/local/django/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint
RUN chmod +x /entrypoint

COPY ./docker/local/django/start /start
RUN sed -i 's/\r//' /start
RUN chmod +x /start

COPY ./docker/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r//' /start-celeryworker
RUN chmod +x /start-celeryworker

COPY ./docker/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r//' /start-celerybeat
RUN chmod +x /start-celerybeat

COPY ./docker/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r//' /start-flower
RUN chmod +x /start-flower

WORKDIR /app

ENTRYPOINT ["/entrypoint"]
