FROM python:3.12.10-slim

WORKDIR /app

# LightGBM's prebuilt wheel needs the OpenMP runtime
RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Models and app.db live here: mount a volume so they survive redeploys
VOLUME /app/data

# Expose port
EXPOSE 8000

# One worker only: the scheduler runs inside this process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
