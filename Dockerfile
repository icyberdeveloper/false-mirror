FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update && apt-get install shadowsocks-libev

RUN pip install -r requirements.txt

COPY ./ /app

RUN chmod +x entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]