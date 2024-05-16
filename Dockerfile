FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./

RUN pip install -r requirements.txt
RUN sudo apt install shadowsocks-libev

COPY ./ /app

CMD [ "python", "main.py" ]