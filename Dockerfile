# Start from official Python 3.12 slim image
# "slim" means minimal OS — no extra packages we don't need
# This keeps the image small (~50MB vs ~900MB for the full image)
FROM python:3.12-slim

# Set working directory inside the container
# All subsequent commands run from here
WORKDIR /app

# Copy requirements first — before copying your code
# WHY: Docker caches each layer. If requirements.txt hasn't changed,
# Docker skips the pip install step entirely on next build.
# If you copied all files first, any code change would bust this cache.
COPY requirements.txt .

# Install dependencies
# --no-cache-dir: don't store pip cache inside the image (saves space)
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of your code
# This layer changes often so it comes AFTER the slow pip install layer
COPY . .

# Tell Docker this container doesn't listen on a network port
# (your Telegram bot uses polling, not a server — but FastAPI does use a port)
# Railway will inject the PORT env var at runtime
EXPOSE 8080

# The command that runs when the container starts
# Use CMD not RUN — RUN executes at build time, CMD at runtime
CMD ["python", "main.py"]