###############################################################################
# XBWorld AI Agent
#
# Connects to a remote xbworld-server and plays the game using LLM.
#
# Build:
#   docker build -t xbworld-agent .
#
# Run:
#   docker run -e XBWORLD_HOST=your-server -e LLM_API_KEY=... xbworld-agent
###############################################################################

FROM python:3.11-slim-bookworm

COPY requirements.txt /app/
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py /app/

RUN useradd -m -s /bin/bash xbworld && \
    chown -R xbworld:xbworld /app
ENV PYTHONUNBUFFERED=1
USER xbworld

CMD ["python3", "run_remote.py"]
