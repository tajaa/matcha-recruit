"""Slack bot integration for the agent.

Uses Socket Mode (no public URL needed). Listens for messages in configured
channels and forwards them to the agent's chat logic.

Requires:
    SLACK_BOT_TOKEN  — Bot User OAuth Token (xoxb-...)
    SLACK_APP_TOKEN  — App-Level Token with connections:write scope (xapp-...)

Setup:
    1. Create a Slack app at https://api.slack.com/apps
    2. Enable Socket Mode (Settings > Socket Mode)
    3. Create an App-Level Token with connections:write scope
    4. Add bot scopes: chat:write, channels:history, groups:history, im:history
    5. Subscribe to events: message.channels, message.groups, message.im
    6. Install app to workspace
    7. Invite the bot to your channel: /invite @matcha-agent
"""

import asyncio
import logging
import os
import threading

logger = logging.getLogger("agent.slack")


class SlackBot:
    """Slack bot that forwards messages to the agent."""

    def __init__(self, sandbox, config):
        self.sandbox = sandbox
        self.config = config
        self.bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        self.app_token = os.getenv("SLACK_APP_TOKEN", "")
        self._thread: threading.Thread | None = None
        self._bot_user_id: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.app_token)

    def start(self):
        """Start the Slack bot in a background thread."""
        if not self.is_configured:
            logger.info("Slack not configured (missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN)")
            return

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Slack bot starting in background")

    def _run(self):
        """Run the Slack socket mode handler (blocking)."""
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler

            app = App(token=self.bot_token)

            # Get our own bot user ID so we can ignore our own messages
            auth = app.client.auth_test()
            self._bot_user_id = auth["user_id"]
            logger.info(f"Slack bot connected as <@{self._bot_user_id}>")

            @app.event("message")
            def handle_message(event, say):
                # Ignore bot's own messages and message subtypes (edits, joins, etc.)
                if event.get("subtype"):
                    return
                if event.get("user") == self._bot_user_id:
                    return
                if event.get("bot_id"):
                    return

                text = event.get("text", "").strip()
                if not text:
                    return

                thread_ts = event.get("thread_ts") or event.get("ts")

                # Run the async agent chat in a new event loop
                try:
                    response = asyncio.run(self._chat(text))
                    say(text=response, thread_ts=thread_ts)
                except Exception as e:
                    logger.error(f"Slack chat error: {e}")
                    say(text=f"Error: {e}", thread_ts=thread_ts)

            self.sandbox.slack_connected = True
            handler = SocketModeHandler(app, self.app_token)
            handler.start()  # Blocking

        except ImportError:
            logger.warning("slack_bolt not installed — run: pip install slack_bolt")
        except Exception as e:
            logger.error(f"Slack bot failed to start: {e}")
            self.sandbox.slack_connected = False

    async def _chat(self, message: str) -> str:
        """Send a message to the agent LLM and return the response."""
        prompt = f"""You are matcha-agent, a helpful assistant in a Slack channel.
You can discuss files, provide analysis, and answer questions.
Be concise and direct. Use Slack-friendly formatting (*bold*, _italic_, `code`).

User: {message}"""

        return await self.sandbox.llm.generate(prompt)
