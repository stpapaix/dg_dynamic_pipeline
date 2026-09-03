# dg_dynamic_pipeline

Modernizing a Microsoft Fabric **Data Factory pipeline** (`ops_pipeline3`) into a **Spark notebook**, with fully automated **CI/CD deployment** to a Fabric workspace via a service principal and GitHub Actions.

---

## What this repo does

1. **Authenticates to Microsoft Fabric non-interactively** using an Entra ID service principal (no browser login).
2. **Deploys Fabric items** (notebooks) into a workspace from GitHub Actions — the client secret is stored as a GitHub secret, never in the repo.
3. **Replaces the `ops_pipeline3` data pipeline with a PySpark notebook** that does the same metadata-driven incremental ingestion from an Eventhouse (KQL database) into Lakehouse Delta tables.
4. **Produces a customer-facing PDF** explaining the pipeline, the notebook, and the scaling considerations.

---

## Repository layout

| Path | Purpose |
|------|---------|
| [src/auth.py](src/auth.py) | `ClientSecretCredential` + `get_fabric_token()` — service-principal auth for the Fabric REST API. |
| [src/fabric_client.py](src/fabric_client.py) | Minimal REST client; lists workspaces/items to verify authentication. |
| [src/deploy_notebook.py](src/deploy_notebook.py) | Create-or-update a Fabric Notebook item from a local `.ipynb` (idempotent). |
| [src/fetch_pipeline.py](src/fetch_pipeline.py) | Fetch a pipeline's JSON definition via the Fabric REST API. |
| [notebooks/hello_world.ipynb](notebooks/hello_world.ipynb) | Smoke-test notebook used to validate the deploy pipeline. |
| [notebooks/replace_ops_pipeline3.ipynb](notebooks/replace_ops_pipeline3.ipynb) | **The Spark replacement for `ops_pipeline3`.** |
| [reports/generate_report.py](reports/generate_report.py) | Builds the customer PDF from the notebook + explanatory text. |
| [reports/ops_pipeline3_explained.pdf](reports/ops_pipeline3_explained.pdf) | The generated customer document (3 chapters). |
| [data/ops_pipeline3.zip](data/ops_pipeline3.zip) | The exported source pipeline used for analysis. |
| [.github/workflows/deploy.yml](.github/workflows/deploy.yml) | CI/CD: authenticate and deploy the notebooks to Fabric. |
| [requirements.txt](requirements.txt) | Python dependencies (`azure-identity`, `requests`, `python-dotenv`). |
| [.env.example](.env.example) | Template for the non-secret IDs (copy to `.env`). |

---

## 1. Authentication & CI/CD setup

Based on the **fabric-auth-skill**. Non-interactive service-principal authentication drives the deployment.

### One-time configuration
1. **Register an app** in Entra ID → record the **Client ID**, **Tenant ID**, and create a **client secret**.
2. **Enable service principals in the Fabric Admin portal** → Tenant settings → *"Service principals can use Fabric APIs"*. (Skipping this is the #1 cause of `401/403`.)
3. **Grant the SP access** to the target workspace (Member/Admin).
4. **Store credentials in GitHub** → repo *Settings → Secrets and variables → Actions*:
   - **Secret:** `AZURE_CLIENT_SECRET`
   - **Variables:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `FABRIC_WORKSPACE_ID`

### How deployment runs
On push to `main` (or manual dispatch), [deploy.yml](.github/workflows/deploy.yml):
1. installs dependencies,
2. verifies auth with `fabric_client.py`,
3. deploys `hello_world.ipynb` and `replace_ops_pipeline3.ipynb` into the workspace via `deploy_notebook.py`.

### Key facts
- Fabric API scope: `https://api.fabric.microsoft.com/.default`
- Fabric REST base: `https://api.fabric.microsoft.com/v1`
- `load_dotenv()` does not override real env vars, so the GitHub-injected secret always wins over any local `.env`.

---

## 2. The `ops_pipeline3` replacement

### What the original pipeline does
`ops_pipeline3` is a **metadata-driven incremental ingestion** pipeline:

```
datacopyjobsetup → LookupDueJobs → ForEach → Copy (KQL → Lakehouse) → Delta tables
```

- **LookupDueJobs (Lookup)** reads every row of the control table `dbo.datacopyjobsetup`. Each row = one copy job with `SourceName`, `WatermarkColumn`, `LastUpdated`, `DestinationName`.
- **ForEach (batchCount 20)** loops over those rows. For each, a **Copy** activity pulls from the Eventhouse with a dynamic KQL query
  `<SourceName> | where <WatermarkColumn> > datetime(<LastUpdated>)`
  and appends to the Lakehouse Delta table `dbo.<DestinationName>`.

### The notebook
[notebooks/replace_ops_pipeline3.ipynb](notebooks/replace_ops_pipeline3.ipynb) reproduces this in PySpark:
- reads the control table and each destination via **absolute OneLake paths** (no attached lakehouse required),
- authenticates to the Eventhouse with the notebook identity (`notebookutils.credentials.getToken`),
- reads each incremental KQL query and appends to the destination Delta table,
- includes an optional cell to **advance the watermark** (the original pipeline never did).

### Parameters to set
| Parameter | Value |
|-----------|-------|
| `kql_cluster` | Eventhouse query URI |
| `kql_database` | KQL **database UID (GUID)** — not the display name |
| `workspace_id` | target workspace GUID |
| `lakehouse_id` | `ops_lakehouse` artifact GUID |
| `max_parallel` | concurrency (see scaling below) |

---

## 3. Parallelism & scaling notes

The Eventhouse (not the notebook) is the bottleneck. Two reader modes:

- **Single (query) mode** — simple, but capped at **500,000 rows** per query. Small tables only.
- **Distributed mode** — reads via `.export`; **no row cap**, but each export consumes an export slot.

The Eventhouse export capacity was **1**, so parallel reads were throttled. Concurrent exports scale with compute:

> concurrent exports ≈ total cores × 0.75

So `max_parallel = 8` needs ~**11 warm cores**. On an **F64** capacity, raise the Eventhouse **Minimum consumption** (Eventhouse → Capacity Planner) and confirm with `.show capacity` (Export row) before increasing `max_parallel`. The notebook keeps a retry-with-backoff as a safety net.

The current setting is `max_parallel = 1` (sequential, distributed mode) — correct and safe on Capacity 1.

---

## Local usage

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env      # fill in the IDs only
$env:AZURE_CLIENT_SECRET = "<paste-secret>"   # secret stays out of files

python src/fabric_client.py                        # verify auth
python src/deploy_notebook.py                       # deploy hello_world
python src/deploy_notebook.py notebooks/replace_ops_pipeline3.ipynb replace_ops_pipeline3
python reports/generate_report.py                   # regenerate the PDF
```

---

## Deliverables produced in this project
- ✅ Service-principal auth + GitHub Actions CI/CD to Fabric.
- ✅ `HelloWorld` and `replace_ops_pipeline3` notebooks deployed to the `Test4Vlad` workspace.
- ✅ PySpark notebook replacing the `ops_pipeline3` pipeline (lookup + foreach copy).
- ✅ Customer PDF: [reports/ops_pipeline3_explained.pdf](reports/ops_pipeline3_explained.pdf).
