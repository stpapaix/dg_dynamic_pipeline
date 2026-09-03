"""Fetch the JSON definition of a Fabric data pipeline via the REST API and print
a parsed activity summary.

Uses the service-principal credential (same AZURE_* env vars as GitHub Actions)
when available, otherwise falls back to an interactive browser sign-in.

Usage:
    python src/fetch_pipeline.py <workspace_id> <pipeline_id> [tenant_id]
"""

import base64
import json
import os
import sys
import time

import requests
from azure.identity import ClientSecretCredential, InteractiveBrowserCredential
from dotenv import load_dotenv

load_dotenv()

FABRIC_API = os.environ.get("FABRIC_API_BASE", "https://api.fabric.microsoft.com/v1")
FABRIC_SCOPE = os.environ.get("FABRIC_SCOPE", "https://api.fabric.microsoft.com/.default")
DEFAULT_TENANT = "72f988bf-86f1-41af-91ab-2d7cd011db47"  # microsoft.com corp tenant
_TIMEOUT = 60


def _credential(tenant_id: str):
    """Prefer the service principal (non-interactive); fall back to browser sign-in."""
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")
    sp_tenant = os.environ.get("AZURE_TENANT_ID", tenant_id)
    if client_id and client_secret:
        return ClientSecretCredential(sp_tenant, client_id, client_secret)
    return InteractiveBrowserCredential(tenant_id=tenant_id)


def _headers(cred: InteractiveBrowserCredential) -> dict:
    token = cred.get_token(FABRIC_SCOPE).token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get_definition_body(workspace_id: str, pipeline_id: str, headers: dict) -> dict:
    url = f"{FABRIC_API}/workspaces/{workspace_id}/items/{pipeline_id}/getDefinition"
    resp = requests.post(url, headers=headers, timeout=_TIMEOUT)

    if resp.status_code == 202:
        location = resp.headers["Location"]
        retry_after = int(resp.headers.get("Retry-After", "3"))
        while True:
            time.sleep(retry_after)
            poll = requests.get(location, headers=headers, timeout=_TIMEOUT)
            poll.raise_for_status()
            status = poll.json().get("status")
            if status in ("Succeeded", "Completed"):
                result = requests.get(
                    f"{location}/result", headers=headers, timeout=_TIMEOUT
                )
                result.raise_for_status()
                return result.json()
            if status == "Failed":
                raise RuntimeError(f"getDefinition failed: {poll.text}")
    resp.raise_for_status()
    return resp.json()


def _decode_parts(body: dict) -> dict[str, str]:
    parts: dict[str, str] = {}
    for part in body["definition"]["parts"]:
        if part["payloadType"] == "InlineBase64":
            parts[part["path"]] = base64.b64decode(part["payload"]).decode("utf-8")
        else:
            parts[part["path"]] = f"(payloadType={part['payloadType']})"
    return parts


def _summarize_activities(content: dict) -> None:
    props = content.get("properties", content)
    activities = props.get("activities", [])
    params = props.get("parameters", {})
    variables = props.get("variables", {})

    print("\n========== SUMMARY ==========")
    if params:
        print(f"\nParameters ({len(params)}):")
        for name, spec in params.items():
            print(f"  - {name}: type={spec.get('type')} default={spec.get('defaultValue')}")
    if variables:
        print(f"\nVariables ({len(variables)}):")
        for name, spec in variables.items():
            print(f"  - {name}: type={spec.get('type')} default={spec.get('defaultValue')}")

    def walk(acts: list, indent: int = 0) -> None:
        pad = "  " * indent
        for act in acts:
            name = act.get("name")
            atype = act.get("type")
            deps = [d.get("activity") for d in act.get("dependsOn", [])]
            dep_str = f"  (depends on: {', '.join(deps)})" if deps else ""
            print(f"{pad}- [{atype}] {name}{dep_str}")
            inner = act.get("typeProperties", {})
            nested = inner.get("activities")
            if nested:
                walk(nested, indent + 1)

    print(f"\nActivities ({len(activities)}):")
    walk(activities)


def get_pipeline_definition(workspace_id: str, pipeline_id: str, tenant_id: str) -> None:
    cred = _credential(tenant_id)
    headers = _headers(cred)
    body = _get_definition_body(workspace_id, pipeline_id, headers)
    parts = _decode_parts(body)

    for path, text in parts.items():
        print(f"\n===== {path} =====")
        print(text)

    for path, text in parts.items():
        if path.endswith("pipeline-content.json"):
            try:
                _summarize_activities(json.loads(text))
            except json.JSONDecodeError:
                pass


def main() -> None:
    workspace_id = sys.argv[1]
    pipeline_id = sys.argv[2]
    tenant_id = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_TENANT
    get_pipeline_definition(workspace_id, pipeline_id, tenant_id)


if __name__ == "__main__":
    main()
