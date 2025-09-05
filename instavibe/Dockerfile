FROM python:3.12-slim
WORKDIR /app

COPY ./instavibe/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./agents/a2a_common-0.1.0-py3-none-any.whl ./agents/a2a_common-0.1.0-py3-none-any.whl
RUN pip install --no-cache-dir ./agents/a2a_common-0.1.0-py3-none-any.whl

COPY ./instavibe/ ./
COPY ./common ./common

ENV PYTHONPATH="/app"
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
