FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e libs/domain -e services/messaging

CMD ["python", "-c", "import ubunturemit_messaging; print('Messaging Service ready')"]
