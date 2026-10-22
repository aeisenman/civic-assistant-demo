# deploy/aws — running the demo on EC2 with Bedrock

One EC2 instance, the same `docker compose` stack as your laptop, and a LiteLLM
gateway in front of Bedrock so the application code does not change. The API
still speaks the OpenAI protocol; only `.env` is different.

## What is here

| File | What it does |
|---|---|
| `up.sh` | Creates the IAM role, the security group and the instance, ships the repo, starts compose. |
| `down.sh` | Terminates the instance and deletes the security group. Leaves the IAM role. |
| `litellm.yaml` | Maps the tier aliases (`small`, `smart`, `escalate`, `extract`, `embed`) to Bedrock model ids. |

The five ids it maps, all us-west-2 cross-region inference profiles:

| Alias | Bedrock model | Why |
|---|---|---|
| `small` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | intent classification; routing accuracy matters and it is still cheap |
| `smart` | `us.anthropic.claude-sonnet-4-6` | resident-facing answers with tools and RAG |
| `escalate` | `us.anthropic.claude-opus-4-6-v1` | low-confidence, high-complexity or multi-intent turns |
| `extract` | `us.amazon.nova-lite-v1:0` | uploaded forms: 300k context at $0.06/$0.24 per 1M tokens |
| `embed` | `amazon.titan-embed-text-v2:0` | knowledge-base and query embeddings, 1024 dims |

## Exact commands

```bash
# once: an EC2 key pair whose .pem is at ~/.ssh/<name>.pem
export KEY_NAME=my-keypair

bash deploy/aws/up.sh          # ~10 minutes, mostly the docker build
# prints http://<ip>:3001 (chat), /staff, /traces and http://<ip>:8080/health,
# then the staff password, the LiteLLM master key and the S3 secret it generated

bash deploy/aws/down.sh        # terminates the instance, deletes the SG
```

Overrides, all environment variables: `REGION` (default `us-west-2`),
`INSTANCE_TYPE` (default `t3.large`), `REPO_DIR` (default the repo root),
`SSH_KEY` (default `~/.ssh/$KEY_NAME.pem`).

Both scripts are idempotent. `up.sh` looks each resource up by name before
creating it, so re-running it re-syncs the code onto the existing instance
rather than launching a second one — and re-generates the credentials, so the
password printed by the newest run is the one that works.

## Credentials

`.env.bedrock` is committed with working demo values (`STAFF_PASSWORD=staff`,
`LLM_API_KEY=sk-litellm-demo`, `S3_SECRET_KEY=civicsecret`). Those are in git and
therefore public, so `up.sh` does not deploy them. It writes `ENVIRONMENT=prod`
into the instance's `.env`, which turns on the denylist in `api/app/config.py`:
the API refuses to start if any of `STAFF_PASSWORD`, `S3_SECRET_KEY`,
`LLM_API_KEY` or `EMBED_API_KEY` is still a placeholder, or if `WEB_ORIGIN` still
says `localhost`. Then it generates real ones with `openssl rand -base64 24`:

| Value | Where it lands | Notes |
|---|---|---|
| `STAFF_PASSWORD` | instance `.env`; the seed loader re-hashes it at startup | this is the `/staff` and `/traces` sign-in |
| `LITELLM_MASTER_KEY` | instance `.env`; the gateway reads it via `master_key: os.environ/LITELLM_MASTER_KEY` | also copied into `LLM_API_KEY` and `EMBED_API_KEY`, which are the same secret seen from the API's side |
| `S3_SECRET_KEY` | instance `.env` | SeaweedFS only checks S3 signatures once an identity config is loaded and this stack loads none, so it is accepted whatever it says — generated anyway, because the validator cannot know that and because the day someone adds `-s3.config` it should already be real |

They are printed **once**, at the end of `up.sh`, and exist nowhere else but
`/home/ubuntu/app/.env` on the instance, which `down.sh` destroys. Lost one?
`ssh` in and `grep` the file, or re-run `up.sh`.

## A Bedrock-only AWS profile for local testing

On EC2 the LiteLLM container gets its credentials from the instance role and no
keys are copied anywhere. Locally there is no instance role, so `docker-compose.yml`
mounts one credentials file read-only and names one profile in it:

```yaml
    volumes:
      - ${AWS_SHARED_CREDENTIALS_FILE:-~/.aws/credentials}:/root/.aws/credentials:ro
    environment:
      AWS_PROFILE: ${AWS_PROFILE:-default}
```

This replaced `~/.aws:/root/.aws:ro`, which handed the container the developer's
entire AWS identity — every profile, every account — while it processes untrusted
resident text. **Point it at a profile that can do nothing but Bedrock
inference.** One way to make one:

```bash
# 1. a user with only the four inference actions, same as the instance role
aws iam create-user --user-name bedrock-local
aws iam put-user-policy --user-name bedrock-local --policy-name bedrock-invoke \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream",
              "bedrock:Converse","bedrock:ConverseStream"],"Resource":"*"}]}'

# 2. a key pair for it, written into a profile of its own
aws iam create-access-key --user-name bedrock-local        # note the two values
aws configure --profile bedrock-local                      # paste them here

# 3. tell compose to use it
echo 'AWS_PROFILE=bedrock-local' >> .env
```

If you keep everything in the default `~/.aws/credentials`, that whole file is
still inside the container even though only one profile is selected — put the
Bedrock user in a file of its own and set `AWS_SHARED_CREDENTIALS_FILE` to it if
that matters to you.

On the instance, `up.sh` writes `/home/ubuntu/.aws/credentials` containing just
`[default]` with no keys. botocore resolves the profile, finds nothing in it, and
falls through to the instance role. Without the file docker would create a
*directory* at that path, which is a confusing thing to debug.

## What it costs

- `t3.large` on-demand in us-west-2 is about $0.083/hour, so roughly **$2 per
  day** if you leave it running, plus a few cents for the 40 GB gp3 volume.
- Bedrock is per token. The demo's own traffic is trivial: a measured 30-item
  eval run at the tier prices in `.env.bedrock` cost **$0.4991**, about 1.7
  cents a turn. Startup embeds the whole knowledge base once, for well under a
  cent.
- Nothing is free-tier. Run `down.sh` when the demo is over.

## What it does not do

- **No TLS and no domain.** Ports 3001 and 8080 are plain HTTP. They are now
  restricted to the public IP of whoever ran `up.sh` (`${MY_IP}/32`, the same
  rule SSH always had), so the session cookie only crosses that one link in the
  clear — but it does cross it in the clear. Fine for a scheduled demo from a
  known network, not for anything else. Sharing the URL with a colleague means
  re-running `up.sh` from their network, or adding their `/32` by hand. See
  "Putting TLS in front of it" below for the two shapes that fix this; note that
  `ENVIRONMENT=prod` refuses a plain `http://` `WEB_ORIGIN`, so `up.sh` writing
  `ENVIRONMENT=prod` and a plaintext origin is a combination that will not boot.
- **One gateway container.** `deploy/aws/litellm.yaml` now falls back from
  `escalate` to `smart` when Opus is throttled, and every model id is a `us.`
  cross-region profile, so Bedrock handles a regional event itself — but the
  LiteLLM container is still a single process on a single box, and `api`
  `depends_on` it under the `aws` profile.
- **No backups on the instance.** `scripts/backup.sh` exists and runs locally;
  nothing schedules it on EC2.
- **No OCR.** Scanned PDFs are stored and reported as unreadable, exactly as
  they are locally.
- **No backups and no persistence guarantees.** Postgres and SeaweedFS write to
  the instance's EBS volume; terminating the instance destroys them.
- **No autoscaling, no load balancer, no health-check-driven restarts.** It is
  one box running `docker compose`.

## Putting TLS in front of it (documentation only — `up.sh` does none of this)

Nothing below is automated. It is written down because `ENVIRONMENT=prod` now
refuses to start with a plain `http://` `WEB_ORIGIN` (audit finding 8), so a
real deploy has to terminate TLS somewhere, and these are the two shapes that
fit this stack. Both leave the API code untouched: uvicorn already runs with
`--proxy-headers --forwarded-allow-ips="*"`, so it reads `X-Forwarded-Proto`
and the staff cookie is marked `Secure` on its own.

**Option A — Caddy on the same box** (matches PRODUCTION_PLAN.md option A).
Add one service to `docker-compose.yml`, publish 80 and 443 instead of 3001 and
8080, and give it a two-line Caddyfile: `civic.example.gov` reverse-proxying `/`
to `web:3000` and `/api/*` plus `/health` to `api:8080`. Caddy gets a
Let's Encrypt certificate on first boot and renews it itself, which is why it is
the shorter path than nginx + certbot here. Then set `WEB_ORIGIN=https://civic.example.gov`
and, because everything is one origin, `NEXT_PUBLIC_API_URL=https://civic.example.gov`.
Open 80 and 443 to the world (ACME's HTTP-01 challenge needs 80 reachable) and
close 3001/8080 entirely. Needs a DNS A record pointing at the elastic IP.

**Option B — an ALB** (matches option B). An HTTPS:443 listener with an ACM
certificate, two target groups (`/api/*` and `/health` to the api target, `/`
to the web target), a redirect from HTTP:80, and a security group on the
instance that accepts 3001/8080 only from the ALB's security group. ACM renews
the certificate; nothing runs on the box.

**Load balancer idle timeout must exceed `LLM_TIMEOUT_S` (45 s); set it to
120 s.** An ALB defaults to 60 s of idle time, and "idle" means no bytes in
either direction — a chat turn whose first token is still 50 s away looks idle
the whole time. The connection is then dropped mid-answer with no resume and,
today, no heartbeat to keep it busy (audit finding 17; M26a adds a `: heartbeat`
comment every 15 s, which is a second belt, not a replacement for this setting).
`aws elbv2 modify-load-balancer-attributes --attributes
Key=idle_timeout.timeout_seconds,Value=120`. Caddy has no equivalent default to
raise; its read/write timeouts are unset unless you set them.

## Security notes

The instance role carries one inline policy allowing only `bedrock:InvokeModel`,
`bedrock:InvokeModelWithResponseStream`, `bedrock:Converse` and
`bedrock:ConverseStream`. `AmazonBedrockFullAccess` would also grant model
management and provisioned throughput, which the demo has no reason to hold.
SSH is restricted to the public IP of whoever ran `up.sh`; re-run the script
from a new network and it adds that IP too.

SSH, 3001 and 8080 are all restricted to `${MY_IP}/32`. `up.sh` revokes the
world-open `0.0.0.0/0` rules on 3001 and 8080 first, so a security group left
behind by an older run of this script is narrowed rather than left with a
permissive rule sitting next to the new one.

AWS credentials never reach the instance. LiteLLM inside the container picks up
the instance role through the EC2 metadata service; the credentials file that
`docker-compose.yml` mounts holds an empty `[default]` section there. Locally
that mount should point at a Bedrock-only profile — see above.

Every application secret is generated per deploy and printed once. Nothing that
is committed to this repository is ever deployed: `ENVIRONMENT=prod` makes the
API refuse to start if it were.
