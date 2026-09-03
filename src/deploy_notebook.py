"""Deploy a local .ipynb file as a Notebook item into a Microsoft Fabric workspace.

Usage:
    python src/deploy_notebook.py [path-to-ipynb] [display-name]

Defaults to deploying notebooks/hello_world.ipynb as "HelloWorld".
Reuses the service-principal auth from auth.py.
"""

import base64
import os
import sys
import time

import requests
from dotenv import load_dotenv

from auth import get_fabric_token

load_dotenv()

FABRIC_API = "https://api.fabric.microsoft.com/v1"
_TIMEOUT = 60

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_NOTEBOOK = os.path.join(_REPO_ROOT, "notebooks", "hello_world.ipynb")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_fabric_token()}",
        "Content-Type": "application/json",
    }


def _require_workspace_id() -> str:
    workspace_id = os.environ.get("FABRIC_WORKSPACE_ID")
    if not workspace_id:
        raise EnvironmentError(
            "FABRIC_WORKSPACE_ID is not set. Add it to .env or your shell session."
        )
    return workspace_id


def _encode_notebook(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _find_existing_notebook(workspace_id: str, display_name: str) -> str | None:
    resp = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/notebooks",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    for item in resp.json().get("value", []):
        if item.get("displayName") == display_name:
            return item.get("id")
    return None


def _wait_for_operation(resp: requests.Response) -> None:
    """Poll the long-running-operation URL until the deploy finishes."""
    location = resp.headers.get("Location")
    if not location:
        return
    retry_after = int(resp.headers.get("Retry-After", "5"))
    while True:
        time.sleep(retry_after)
        poll = requests.get(location, headers=_headers(), timeout=_TIMEOUT)
        poll.raise_for_status()
        status = poll.json().get("status")
        print(f"  operation status: {status}")
        if status in ("Succeeded", "Completed"):
            return
        if status == "Failed":
            raise RuntimeError(f"Deployment failed: {poll.text}")
        retry_after = int(poll.headers.get("Retry-After", str(retry_after)))


def deploy_notebook(path: str, display_name: str) -> None:
    workspace_id = _require_workspace_id()
    payload = {
        "displayName": display_name,
        "definition": {
            "format": "ipynb",
            "parts": [
                {
                    "path": "notebook-content.ipynb",
                    "payload": _encode_notebook(path),
                    "payloadType": "InlineBase64",
                }
            ],
        },
    }

    existing_id = _find_existing_notebook(workspace_id, display_name)
    if existing_id:
        print(f"Updating existing notebook '{display_name}' ({existing_id})...")
        resp = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/notebooks/{existing_id}/updateDefinition",
            headers=_headers(),
            json={"definition": payload["definition"]},
            timeout=_TIMEOUT,
        )
    else:
        print(f"Creating notebook '{display_name}' in workspace {workspace_id}...")
        resp = requests.post(
            f"{FABRIC_API}/workspaces/{workspace_id}/notebooks",
            headers=_headers(),
            json=payload,
            timeout=_TIMEOUT,
        )

    if resp.status_code == 202:
        _wait_for_operation(resp)
    else:
        resp.raise_for_status()

    print(f"Done. Notebook '{display_name}' deployed successfully.")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_NOTEBOOK
    display_name = sys.argv[2] if len(sys.argv) > 2 else "HelloWorld"
    deploy_notebook(path, display_name)


if __name__ == "__main__":
    main()
