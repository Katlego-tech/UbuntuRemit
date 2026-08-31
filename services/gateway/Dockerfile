FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir \
    -e libs/domain \
    -e services/messaging \
    -e services/asco \
    -e services/audit \
    -e services/rails \
    -e services/gateway

EXPOSE 8000
CMD ["uvicorn", "ubunturemit_gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
