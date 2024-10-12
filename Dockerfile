FROM python:3.12

WORKDIR /app
COPY ./ /app/
RUN ./setup.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["-h"]
