# Security and data handling

Conversation transcripts, model responses, API keys, GitHub tokens, and local
compatibility records are runtime data. They are excluded from version control.

- Copy `.env.example` to `.env`; never put credentials in tracked files.
- Put private input in `input/conversation.txt`, which is ignored.
- Treat everything under `output/` as potentially sensitive.
- Review extracted content before using any publishing code.
- The test suite uses fakes and does not call model-provider or GitHub APIs.

If a secret is ever committed, revoke it first, then remove it from history.

