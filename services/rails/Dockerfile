FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e libs/domain -e services/messaging -e services/asco -e services/rails

CMD ["python", "-c", "import ubunturemit_rails; print('Rails Service ready')"]
