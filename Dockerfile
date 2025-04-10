FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY newznab_mock.py .
COPY newznab_categories.csv .

# Create directories for data and nzbs
RUN mkdir -p /data/nzb_files

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=5000
ENV EXTERNAL_URL=http://localhost:5000
ENV API_KEY=mock_api_key

# Volume for NZB files and configuration
VOLUME ["/app/nzb_files"]

# Expose the port
EXPOSE ${PORT}

# Start the application
ENTRYPOINT python /app/newznab_mock.py \
            --host ${HOST} \
            --port ${PORT} \
            --external-url ${EXTERNAL_URL} \
            --api-key ${API_KEY} \
            --nzb-path /data/nzb_files \
            --nzb-config /data/nzbs.json
