# Recorded first use

This output was produced by the included example with network connections disabled. Synthetic provider or worker replies are identified by the example; no real model quality or billing is implied.

From the installed checkout:

```sh
python -m examples.offline_case
```

[Complete recorded output](result.json)

```text
{
  "mode": "Actual coordinator; synthetic provider response",
  "source": "User: Make a review queue. Require approval before publishing any item.",
  "request_roles": [
    "system",
    "user"
  ],
  "captured_response": {
    "project_title": "Workshop Review Queue",
    "project_description": "Review proposed work before publication.",
    "source_summary": "Synthetic planning request.",
    "items": [
      {
        "type": "Task",
        "title": "Add a review gate",
        "body": "Require a person to approve each draft.",
        "priority": "High",
        "confidence": "High",
        "phase": "V1",
        "needs_review": true
      }
    ]
  },
  "reviewed_project_title": "Workshop Review Queue",
  "compatibility_status": "supported",
  "published": false,
  "network_calls": 0
}
```

Generated timestamps and synthetic identifiers can change between runs. The demonstrated behavior and input fixture remain inspectable in the adjacent example files.
