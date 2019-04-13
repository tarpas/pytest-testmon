FROM python:3.4
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app

COPY . /usr/src/app

RUN pip install -e .

RUN pytest -v --tb=native
