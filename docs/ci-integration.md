# CI Integration Guide

sfq automatically attaches traceable metadata to API requests when running in CI environments. This enables request tracking through Salesforce `ApiEvent` and `LoginEvent` logs.

## Overview

When sfq detects a CI environment, it automatically adds `x-sfdc-addinfo-` headers to all HTTP requests. These appear in Salesforce Event Log Files under the `AdditionalInfo` field.

## Supported CI Providers

| Provider | Detection Variable |
|----------|-------------------|
| GitHub Actions | `GITHUB_ACTIONS=true` |
| GitLab CI | `GITLAB_CI=true` |
| CircleCI | `CIRCLECI=true` |

## Automatic Headers

### GitHub Actions

| Environment Variable | Header |
|---------------------|--------|
| `GITHUB_RUN_ID` | `x-sfdc-addinfo-run_id` |
| `GITHUB_REPOSITORY` | `x-sfdc-addinfo-repository` |
| `GITHUB_WORKFLOW` | `x-sfdc-addinfo-workflow` |
| `GITHUB_REF` | `x-sfdc-addinfo-ref` |
| `RUNNER_OS` | `x-sfdc-addinfo-runner_os` |

### GitLab CI

| Environment Variable | Header |
|---------------------|--------|
| `CI_PIPELINE_ID` | `x-sfdc-addinfo-pipeline_id` |
| `CI_PROJECT_PATH` | `x-sfdc-addinfo-project_path` |
| `CI_JOB_NAME` | `x-sfdc-addinfo-job_name` |
| `CI_COMMIT_REF_NAME` | `x-sfdc-addinfo-commit_ref_name` |
| `CI_RUNNER_ID` | `x-sfdc-addinfo-runner_id` |

### CircleCI

| Environment Variable | Header |
|---------------------|--------|
| `CIRCLE_WORKFLOW_ID` | `x-sfdc-addinfo-workflow_id` |
| `CIRCLE_PROJECT_REPONAME` | `x-sfdc-addinfo-project_reponame` |
| `CIRCLE_BRANCH` | `x-sfdc-addinfo-branch` |
| `CIRCLE_BUILD_NUM` | `x-sfdc-addinfo-build_num` |

## PII Headers

PII headers are **not included by default**. Enable with:

```bash
export SFQ_ATTACH_CI_PII=true
```

### GitHub Actions PII

| Variable | Header |
|----------|--------|
| `GITHUB_ACTOR` | `x-sfdc-addinfo-pii-actor` |
| `GITHUB_ACTOR_ID` | `x-sfdc-addinfo-pii-actor_id` |
| `GITHUB_TRIGGERING_ACTOR` | `x-sfdc-addinfo-pii-triggering_actor` |

### GitLab CI PII

| Variable | Header |
|----------|--------|
| `GITLAB_USER_LOGIN` | `x-sfdc-addinfo-pii-user_login` |
| `GITLAB_USER_NAME` | `x-sfdc-addinfo-pii-user_name` |
| `GITLAB_USER_EMAIL` | `x-sfdc-addinfo-pii-user_email` |
| `GITLAB_USER_ID` | `x-sfdc-addinfo-pii-user_id` |

### CircleCI PII

| Variable | Header |
|----------|--------|
| `CIRCLE_USERNAME` | `x-sfdc-addinfo-pii-username` |

## Custom Headers

Add your own metadata headers using `SFQ_HEADERS`:

```bash
export SFQ_HEADERS="deployment_id:prod-123|team:backend|version:1.0.0"
```

This creates:
```
x-sfdc-addinfo-deployment_id: prod-123
x-sfdc-addinfo-team: backend
x-sfdc-addinfo-version: 1.0.0
```

### Python Example

```python
import os
from sfq import SFAuth

os.environ['SFQ_HEADERS'] = "deployment_id:deploy-123|environment:production"

sf = SFAuth(
    instance_url="https://your-org.my.salesforce.com",
    client_id="PlatformCLI",
    client_secret="",
    refresh_token="your-refresh-token"
)

# All requests include custom headers
result = sf.query("SELECT Id FROM Account LIMIT 1")
```

## Configuration Options

| Variable | Values | Default |
|----------|--------|---------|
| `SFQ_ATTACH_CI` | `true`, `1`, `yes`, `y` | `true` |
| `SFQ_ATTACH_CI_PII` | `true`, `1`, `yes`, `y` | `false` |
| `SFQ_HEADERS` | `key1:value1\|key2:value2` | None |

## Viewing in Salesforce

Headers appear in:
- **ApiEvent** logs: `AdditionalInfo` field
- **LoginEvent** logs: `AdditionalInfo` field


Query example:
```sql
SELECT LogFile, EventType, CreatedDate 
FROM EventLogFile 
WHERE EventType = 'ApiEvent' 
ORDER BY CreatedDate DESC 
LIMIT 1
```

## Disabling CI Headers

```bash
export SFQ_ATTACH_CI=false
```
