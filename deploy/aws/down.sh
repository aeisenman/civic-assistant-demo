#!/usr/bin/env bash
# Tears down what up.sh created: terminates the instance and deletes the
# security group. The IAM role and instance profile are left in place, because
# they cost nothing and re-creating them costs a propagation wait on every run.
# Usage: bash deploy/aws/down.sh
set -euo pipefail

REGION="${REGION:-us-west-2}"
NAME="civic-agent-demo"
SG_NAME="${NAME}-sg"

aws() { command aws --region "$REGION" "$@"; }

INSTANCE_ID="$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopped" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || true)"

if [ -n "$INSTANCE_ID" ] && [ "$INSTANCE_ID" != "None" ]; then
  echo "terminating $INSTANCE_ID"
  aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null
  aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
  echo "terminated"
else
  echo "no running instance tagged $NAME"
fi

SG_ID="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"
if [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ]; then
  # The ENI can take a moment to detach after termination; retry rather than fail.
  for _ in $(seq 1 12); do
    if aws ec2 delete-security-group --group-id "$SG_ID" >/dev/null 2>&1; then
      echo "deleted security group $SG_ID"
      break
    fi
    sleep 10
  done
else
  echo "no security group named $SG_NAME"
fi

echo
echo "Left in place: IAM role ${NAME}-bedrock-role and instance profile ${NAME}-bedrock-profile."
echo "Remove them by hand if you want a clean account:"
echo "  aws iam delete-role-policy --role-name ${NAME}-bedrock-role --policy-name ${NAME}-bedrock-invoke"
echo "  aws iam remove-role-from-instance-profile --instance-profile-name ${NAME}-bedrock-profile --role-name ${NAME}-bedrock-role"
echo "  aws iam delete-instance-profile --instance-profile-name ${NAME}-bedrock-profile"
echo "  aws iam delete-role --role-name ${NAME}-bedrock-role"
