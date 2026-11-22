ARG RELEASE=latest
FROM afrovending-backend:${RELEASE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates openssl rclone \
 && curl -fsSL -o /tmp/tools.deb https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-100.10.0.deb \
 && apt-get install -y /tmp/tools.deb && rm -rf /tmp/tools.deb /var/lib/apt/lists/*
COPY deploy/backup/nightly.sh /usr/local/bin/nightly.sh
RUN chmod +x /usr/local/bin/nightly.sh && mkdir -p /backups && chown app /backups
USER app
CMD ["/usr/local/bin/nightly.sh", "loop"]
