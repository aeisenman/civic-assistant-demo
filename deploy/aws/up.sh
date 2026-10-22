#!/usr/bin/env bash
# Launches the whole demo on one EC2 instance running Bedrock through LiteLLM.
# Creates (idempotently, by name) an IAM role + instance profile scoped to
# Bedrock inference, a security group, and one Ubuntu 24.04 box; then rsyncs the
# repo, points .env at the Bedrock profile and runs docker compose there.
# Depends on: aws CLI v2 with credentials, an existing EC2 key pair, rsync, ssh.
# Usage: KEY_NAME=my-keypair bash deploy/aws/up.sh
set -euo pipefail

# --- variables ---------------------------------------------------------------
REGION="${REGION:-us-west-2}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.large}"
KEY_NAME="${KEY_NAME:-}"                      # required: an existing EC2 key pair
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/${KEY_NAME}.pem}"

NAME="civic-agent-demo"
ROLE_NAME="${NAME}-bedrock-role"
PROFILE_NAME="${NAME}-bedrock-profile"
POLICY_NAME="${NAME}-bedrock-invoke"
SG_NAME="${NAME}-sg"
REMOTE_DIR="/home/ubuntu/app"
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

[ -n "$KEY_NAME" ] || { echo "set KEY_NAME to an existing EC2 key pair" >&2; exit 1; }
[ -f "$SSH_KEY" ] || { echo "no private key at $SSH_KEY (set SSH_KEY)" >&2; exit 1; }
[ -f "$REPO_DIR/.env.bedrock" ] || { echo "no .env.bedrock in $REPO_DIR" >&2; exit 1; }

aws() { command aws --region "$REGION" "$@"; }
say() { printf '\n== %s\n' "$1"; }

# --- 1. IAM role, scoped to Bedrock inference only ---------------------------
# Scoped deliberately: AmazonBedrockFullAccess also grants model management and
# provisioned throughput, which a demo box has no business being able to do.
say "IAM role $ROLE_NAME"
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version":"2012-10-17",
      "Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},
                    "Action":"sts:AssumeRole"}]}' >/dev/null
  echo "created role"
else
  echo "role exists"
fi

aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow",
                  "Action":["bedrock:InvokeModel",
                            "bedrock:InvokeModelWithResponseStream",
                            "bedrock:Converse",
                            "bedrock:ConverseStream"],
                  "Resource":"*"}]}' >/dev/null
echo "inline policy $POLICY_NAME applied"

if ! aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null
  aws iam add-role-to-instance-profile \
    --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME" >/dev/null
  echo "created instance profile; waiting 10s for IAM to propagate"
  sleep 10
else
  echo "instance profile exists"
fi

# --- 2. security group -------------------------------------------------------
say "security group $SG_NAME"
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)"
SG_ID="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
  "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"

if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  SG_ID="$(aws ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC_ID" \
    --description "civic agent demo: ssh from me, app ports open" \
    --query 'GroupId' --output text)"
  echo "created $SG_ID"
else
  echo "exists: $SG_ID"
fi

MY_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
# `|| true` on each: re-running the script hits "rule already exists", which is
# the idempotent outcome, not a failure.
#
# 3001 and 8080 used to be 0.0.0.0/0. That put a staff queue that can approve
# applications and issue certificates on the open internet over plain HTTP, so
# they now get the same ${MY_IP}/32 treatment the SSH rule always had. The
# revoke comes first for security groups left behind by an earlier run of this
# script: authorizing alone would leave the old world-open rule sitting next to
# the new narrow one, and the permissive rule wins.
for PORT in 22 3001 8080; do
  aws ec2 revoke-security-group-ingress --group-id "$SG_ID" \
    --protocol tcp --port "$PORT" --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --protocol tcp --port "$PORT" --cidr "${MY_IP}/32" >/dev/null 2>&1 || true
done
echo "ssh, 3001 and 8080 open to ${MY_IP}/32 only"
echo "re-run this script from another network to add that address too"

# --- 3. instance -------------------------------------------------------------
say "instance $NAME"
INSTANCE_ID="$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || true)"

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
  # Canonical's SSM parameter always points at the current Ubuntu 24.04 AMI.
  AMI_ID="$(aws ssm get-parameter \
    --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
    --query 'Parameter.Value' --output text)"

  USER_DATA="$(cat <<'CLOUDINIT'
#!/bin/bash
set -eux
apt-get update
apt-get install -y ca-certificates curl rsync
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu
mkdir -p /home/ubuntu/app
chown ubuntu:ubuntu /home/ubuntu/app
touch /home/ubuntu/.provisioned
CLOUDINIT
)"

  INSTANCE_ID="$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile "Name=$PROFILE_NAME" \
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=40,VolumeType=gp3}' \
    --user-data "$USER_DATA" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'Instances[0].InstanceId' --output text)"
  echo "launched $INSTANCE_ID"
else
  echo "reusing $INSTANCE_ID"
fi

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
echo "public ip $PUBLIC_IP"

# --- 4. wait for SSH and for cloud-init to finish installing docker ----------
say "waiting for ssh and docker on $PUBLIC_IP"
for _ in $(seq 1 60); do
  if ssh "${SSH_OPTS[@]}" -i "$SSH_KEY" "ubuntu@$PUBLIC_IP" \
      'test -f /home/ubuntu/.provisioned && docker --version' >/dev/null 2>&1; then
    echo "ready"
    break
  fi
  sleep 10
done
ssh "${SSH_OPTS[@]}" -i "$SSH_KEY" "ubuntu@$PUBLIC_IP" 'docker --version && docker compose version'

# --- 5. ship the repo --------------------------------------------------------
say "rsync $REPO_DIR -> $PUBLIC_IP:$REMOTE_DIR"
rsync -az --delete \
  --exclude 'data/' --exclude 'node_modules/' --exclude '.next/' --exclude '.venv/' \
  --exclude '.git/' --exclude '__pycache__/' --exclude '.pytest_cache/' \
  -e "ssh ${SSH_OPTS[*]} -i $SSH_KEY" \
  "$REPO_DIR/" "ubuntu@$PUBLIC_IP:$REMOTE_DIR/"

# --- 6. generate this deploy's credentials -----------------------------------
# Every secret in .env.bedrock is committed to git and therefore public.
# ENVIRONMENT=prod (written below) makes api/app/config.py refuse to start while
# any of them is still in place, so they are replaced here with fresh random
# values. 24 base64 bytes is 32 characters of ~192 bits, and base64's alphabet
# contains no `|`, `$` or backtick, so the values are safe both in the sed
# expressions and inside the unquoted heredoc below.
say "generating credentials for this deploy"
STAFF_PASSWORD="$(openssl rand -base64 24)"
LITELLM_MASTER_KEY="$(openssl rand -base64 24)"
# SeaweedFS only enforces S3 signatures once an identity config is loaded
# (weed/s3api/auth_credentials.go: isAuthEnabled flips to true only when
# identitiesCount > 0) and this deploy loads none, so any access/secret pair is
# accepted and this value guards nothing on its own. It is generated anyway: the
# config validator cannot know that, and the day someone adds `-s3.config` the
# secret should already be real rather than `civicsecret`.
S3_SECRET_KEY="$(openssl rand -base64 24)"
# Signs the resident_session cookie. Nothing is stored server-side, so this is
# the only thing standing between a leaked session id and someone else's
# conversation; it is on the placeholder denylist for the same reason.
SESSION_SECRET="$(openssl rand -base64 24)"

# --- 7. configure and start --------------------------------------------------
# NEXT_PUBLIC_API_URL is inlined at build time, so the browser needs the public
# IP baked into the web image, not just present in the container's environment.
# WEB_ORIGIN has to move with it: the browser's origin is http://IP:3001, and
# CORS carrying a session cookie cannot use a wildcard, so leaving it pointed at
# localhost made every fetch from the deployed page fail.
say "configuring .env and starting compose"
ssh "${SSH_OPTS[@]}" -i "$SSH_KEY" "ubuntu@$PUBLIC_IP" bash -s <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"
cp .env.bedrock .env

# \$1 key, \$2 value; escaped so they are the remote shell's positional
# parameters, not this script's. Pipe as the sed delimiter because neither a URL
# nor a base64 secret can contain one. (No backticks anywhere in this heredoc:
# it is unquoted, so a backtick here would be command substitution.)
set_env() {
  if grep -q "^\$1=" .env; then
    sed -i "s|^\$1=.*|\$1=\$2|" .env
  else
    echo "\$1=\$2" >> .env
  fi
}

set_env NEXT_PUBLIC_API_URL "http://$PUBLIC_IP:8080"
set_env WEB_ORIGIN "http://$PUBLIC_IP:3001"
# Turns on the placeholder denylist in api/app/config.py. If any of the values
# below were still the committed demo ones, the API would refuse to boot.
set_env ENVIRONMENT prod
set_env STAFF_PASSWORD "$STAFF_PASSWORD"
set_env S3_SECRET_KEY "$S3_SECRET_KEY"
set_env SESSION_SECRET "$SESSION_SECRET"
# The gateway's master key and the two keys the API sends it are one secret in
# three places; rewrite them together or every model call comes back 401.
set_env LITELLM_MASTER_KEY "$LITELLM_MASTER_KEY"
set_env LLM_API_KEY "$LITELLM_MASTER_KEY"
set_env EMBED_API_KEY "$LITELLM_MASTER_KEY"

# docker-compose.yml mounts \$AWS_SHARED_CREDENTIALS_FILE (default
# ~/.aws/credentials) into the LiteLLM container and sets AWS_PROFILE=default.
# On EC2 there are no credentials to mount and none are wanted: an empty
# [default] section is enough for botocore to resolve the profile, find no keys
# in it, and fall through to the instance role, which is scoped to Bedrock
# inference only. Without the file, docker would create a directory at that path.
mkdir -p /home/ubuntu/.aws
[ -s /home/ubuntu/.aws/credentials ] || printf '[default]\n' > /home/ubuntu/.aws/credentials
chmod 600 /home/ubuntu/.aws/credentials

docker compose --profile aws up -d --build
REMOTE

say "done"
cat <<EOF
  chat        http://$PUBLIC_IP:3001
  staff queue http://$PUBLIC_IP:3001/staff
  traces      http://$PUBLIC_IP:3001/traces
  api health  http://$PUBLIC_IP:8080/health
  ssh         ssh -i $SSH_KEY ubuntu@$PUBLIC_IP

The first request is slow: the API embeds the whole knowledge base on startup.
Tear it down with: bash deploy/aws/down.sh

Ports 3001 and 8080 are reachable from ${MY_IP}/32 only, over plain HTTP.

Credentials generated for this deploy. Printed once, here, and nowhere else:
they exist only in $REMOTE_DIR/.env on the instance, which down.sh destroys.

  staff sign-in   staff / $STAFF_PASSWORD
  litellm key     $LITELLM_MASTER_KEY
  s3 secret       $S3_SECRET_KEY
EOF
