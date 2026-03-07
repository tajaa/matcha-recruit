FROM python:3.12-slim

# Non-root user for the agent
RUN groupadd -r agent && useradd -r -g agent -d /app -s /sbin/nologin agent

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code into a proper package
COPY __init__.py agent.py api.py cli.py config.py sandbox.py gmail_auth.py email_check.py ./agent/
COPY skills/ ./agent/skills/
COPY static/ ./agent/static/

# Workspace is mounted at runtime, but create the dir structure
# so the container can start even without the mount
RUN mkdir -p /workspace/inbox /workspace/processed /workspace/output \
    && chown -R agent:agent /workspace /app

USER agent

# Default workspace root inside the container
ENV AGENT_WORKSPACE_ROOT=/workspace

EXPOSE 9100

ENTRYPOINT ["python", "-m", "uvicorn", "agent.api:app", "--host", "0.0.0.0", "--port", "9100"]
CMD []
