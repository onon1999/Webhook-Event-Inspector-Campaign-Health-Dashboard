Build a web application with two core components:
◦ A webhook receiver endpoint (POST /webhook) that accepts incoming JSON
payloads, validates the structure, and stores events in a local data store (SQLite,
JSON file, or in-memory store).
◦ A frontend dashboard that displays: total events received (grouped by event type and
source), a time-series chart showing event volume over the last 24 hours, a
“Campaign Health” panel that flags anomalies (e.g., if email_opened events drop
below a configurable threshold for a given campaign, show a warning indicator).
• Include a “Simulate Events” button or script that sends a batch of sample webhook payloads
to your endpoint so you can demonstrate the dashboard in action without needing live
integrations.
• The dashboard should auto-refresh or use polling/websockets to show new events without a
manual page reload.
• Include basic input validation on the webhook endpoint (reject malformed payloads, return
appropriate HTTP status codes).
• The UI should be clean enough that a non-technical marketing manager could understand
what they are looking at.
