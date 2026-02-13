# Platform Events Guide

sfq supports publishing and subscribing to Salesforce Platform Events for real-time event-driven architectures.

## Overview

Platform Events enable event-based communication between Salesforce and external systems. sfq provides methods to:
- List available Platform Events
- Publish single events
- Publish batch events
- Subscribe to event streams

## Prerequisites

Create a Platform Event in Salesforce:
1. Setup > Platform Events > New Platform Event
2. Define custom fields (e.g., `Message__c`)
3. Note the API name (e.g., `MyEvent__e`)

## Listing Events

```python
from sfq import SFAuth

sf = SFAuth(
    instance_url="https://your-org.my.salesforce.com",
    client_id="PlatformCLI",
    client_secret="",
    refresh_token="your-refresh-token"
)

events = sf.list_events()
print(events)  # ['MyEvent__e', 'AnotherEvent__e', ...]
```

## Publishing Events

### Single Event

```python
result = sf.publish("MyEvent__e", {
    "Message__c": "Hello World",
    "Source__c": "sfq"
})

print(result)
# {'success': True, 'id': '2Ee...'}
```

### Batch Events

Publish multiple events efficiently:

```python
events = [
    {"Message__c": "Event 1", "Priority__c": "High"},
    {"Message__c": "Event 2", "Priority__c": "Low"},
    {"Message__c": "Event 3", "Priority__c": "Medium"}
]

result = sf.publish_batch(events, "MyEvent__e")

for r in result['results']:
    print(f"Success: {r['success']}, ID: {r.get('id')}")
```

## Subscribing to Events (Unstable)

Subscribe to receive events in real-time:

```python
# Subscribe with timeout
for event in sf._subscribe("MyEvent__e", queue_timeout=90):
    data = event.get("data", {})
    payload = data.get("payload", {})
    print(f"Received: {payload.get('Message__c')}")
```

### Subscription Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `event_name` | Platform Event API name | Required |
| `queue_timeout` | Seconds to wait between messages | 90 |
| `max_runtime` | Max seconds to listen (None = unlimited) | None |

### Example: Time-Limited Subscription

```python
import time

# Listen for 5 minutes max
for event in sf._subscribe("MyEvent__e", max_runtime=300):
    data = event.get("data", {})
    print(f"Event received: {data}")
```

### Example: Continuous Listener

```python
def event_listener():
    for event in sf._subscribe("MyEvent__e"):
        try:
            process_event(event)
        except Exception as e:
            print(f"Error processing event: {e}")
            # Continue listening

def process_event(event):
    payload = event["data"]["payload"]
    # Handle the event
    print(f"Processing: {payload}")

event_listener()
```

### Received Event Structure

```python
{
    "channel": "/event/MyEvent__e",
    "data": {
        "event": {
            "createdDate": "2026-01-19T10:30:00.000Z",
            "replayId": 12345
        },
        "payload": {
            "Message__c": "Hello",
            "CreatedById": "005...",
            "CreatedDate": "2026-01-19T10:30:00.000Z"
        }
    }
}
```

## Error Handling

```python
from sfq import SFAuth, APIError

try:
    result = sf.publish("NonExistentEvent__e", {"Message__c": "test"})
except APIError as e:
    print(f"Publish failed: {e}")

# Batch with partial failures
result = sf.publish_batch(events, "MyEvent__e")
for i, r in enumerate(result['results']):
    if not r['success']:
        print(f"Event {i} failed: {r.get('errors')}")
```

## Best Practices

1. **Use batch publishing** for high-volume events
2. **Handle subscription errors** gracefully to maintain the listener; this is not stable.
3. **Set max_runtime** in production to allow graceful shutdown
4. **Monitor replayId** for deduplication if needed
