# Paidly

An AI accounts-receivable copilot for freelancers and small businesses. It chases late invoices and drafts dispute evidence through PayPal's Invoicing and Disputes APIs, with a human approving every outgoing action (sending a reminder, creating an invoice) before it actually happens.

Built for the "Build What's Next with PayPal and AI" hackathon.

## Setup

```powershell
uv venv
.\.venv\Scripts\Activate
uv pip install -r requirements.txt
