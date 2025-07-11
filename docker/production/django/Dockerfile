FROM registry.gitlab.com/a-p-digital/crm-api/python_crm:latest

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements
RUN pip install -r /requirements/production.txt \
    && rm -rf /requirements

COPY ./docker/production/django/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint
RUN chmod +x /entrypoint
RUN chown crm-api /entrypoint

COPY ./docker/production/django/start /start
RUN sed -i 's/\r//' /start
RUN chmod +x /start
RUN chown crm-api /start

COPY ./docker/production/django/websocket/start /start-websockets
RUN sed -i 's/\r//' /start-websockets
RUN chmod +x /start-websockets
RUN chown crm-api /start-websockets

COPY ./docker/production/django/celery/worker/* /
RUN chmod +x /*.sh
RUN chown crm-api /*.sh

COPY ./docker/production/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r//' /start-celerybeat
RUN chmod +x /start-celerybeat
RUN chown crm-api /start-celerybeat

COPY ./docker/production/django/celery/flower/start /start-flower
RUN sed -i 's/\r//' /start-flower
RUN chmod +x /start-flower
RUN chown crm-api /start-flower

COPY ./project /app

RUN chown -R crm-api /app

USER crm-api

WORKDIR /app

EXPOSE 5000

ENTRYPOINT ["/entrypoint"]
