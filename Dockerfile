FROM alpine:latest

RUN echo 'https://mirrors.aliyun.com/alpine/latest-stable/main/' > /etc/apk/repositories
RUN apk update && apk add --no-cache coreutils gcc gdb musl-dev python3

COPY scripts/ /scripts/
RUN chmod +x /scripts/*

USER 33:33
WORKDIR /sandbox
