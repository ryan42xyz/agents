---
metadata:
  kind: structured-triage-trace
  status: final
  sources:
    - runbooks/runbook-aws-iam-access-denied-troubleshooting.md
    - runbooks/runbook-jenkins-s3-permission-troubleshooting.md
  schema_version: "0.1"
  tags: ["aws", "iam", "permissions", "access-denied", "403", "s3"]
  failure_domain: "identity / access control"
  cluster: "Cluster 5 — Identity, permissions, access control"
---

# Structured Triage Trace: Cluster 5 — Identity / Access Control

---

## Signal

```
signals:
  A  AccessDenied / UnauthorizedOperation / 403
  B  "is not authorized to perform" in logs or console
  C  works in dev, fails in prod
  D  can do A but not B (e.g. can get but not list)

→ cluster: Cluster 5 (Identity / Access Control)
→ reason:  all access failures reduce to: who is the identity,
           what do they have permission to do, and what is blocking them
```

### Routing Logic

```
IF   error contains AccessDenied OR UnauthorizedOperation OR 403
THEN triage_path = aws_4layer_permission_walk
     first_action = aws sts get-caller-identity
     (if you skip this, everything after will be wrong)

IF   works_in_dev AND fails_in_prod
THEN suspect = SCP / resource_policy / VPC_endpoint_policy (layer 3-4)
     NOT IAM user policy (layer 2)

IF   explicit_deny in error message
THEN suspect = resource_policy OR SCP (layers 3-4)
     explicit deny overrides allow at any layer
```

---

## Decision Trace

| # | Layer | Action | Tool/Method | Observation | Inference | Confidence |
|---|-------|--------|-------------|-------------|-----------|------------|
| 1 | Who | Confirm caller identity | `aws sts get-caller-identity` | ARN: assumed-role/xxx or IAM user | This is the identity that will be evaluated | 1.00 |
| 2 | IAM policy | Check identity's permissions | AWS IAM console → Policies tab | Missing action (e.g. s3:PutObject) or explicit Deny | 99% of issues are here | 0.85 |
| 3 | Resource policy | Check target resource's policy | `aws s3api get-bucket-policy` / KMS key policy / AMI perms | Deny statement matching identity ARN | Resource is blocking even if IAM allows | 0.80 |
| 4 | Higher layer | Check SCP / boundary / endpoint | AWS Org console → SCPs; VPC endpoint policy | SCP denies action for the account/OU | Org-level block; requires org admin | 0.75 |
| 5 | Network condition | Check VPC/IP constraints in policy | Bucket/resource policy Condition block | `aws:sourceVpc` or `aws:sourceIp` condition | Jenkins agent running outside allowed VPC/IP | 0.80 |

---

## Evidence Chain

```
4_layer_model:
  L1: who is the identity? (aws sts get-caller-identity)
  L2: what does the identity's IAM policy allow/deny?
  L3: does the resource policy allow/deny this identity?
  L4: does SCP / permission boundary / endpoint policy block it?

explicit_deny_logic:
  explicit Deny at ANY layer overrides Allow at all other layers
  → if error says "explicit deny in resource-based policy" → go to L3 first

dev_vs_prod_pattern:
  IF works_in_dev AND fails_in_prod:
    → SCP or resource policy likely (L3/L4)
    → dev account may be outside the SCP scope
    → prod bucket may have more restrictive policy

network_condition_pattern:
  IF error is 403 AND identity has correct permissions:
    → check Condition block in resource policy
    → aws:sourceVpc or aws:sourceIp may exclude Jenkins agent's network
```

---

## Triage Policy (Extracted)

```yaml
policy_name: aws-access-denied-4layer-triage

trigger:
  alert: AccessDenied OR 403 OR UnauthorizedOperation

steps:
  - id: step_1
    action: confirm_caller_identity
    tool: aws_cli
    command: "aws sts get-caller-identity"
    gate: ALWAYS run this first — skip nothing
    output: identity_arn

  - id: step_2
    action: check_iam_policy
    tool: aws_iam_console
    commands:
      - "aws iam list-attached-user-policies --user-name <user>"
      - "aws iam list-attached-role-policies --role-name <role>"
      - "aws iam simulate-principal-policy ..."
    gate: IF explicit deny found → document + fix (#MANUAL)
    on_allow: continue to L3

  - id: step_3
    action: check_resource_policy
    tool: aws_cli
    commands:
      - "aws s3api get-bucket-policy --bucket <bucket>"
      - "aws kms get-key-policy ..."
    gate: IF deny statement matches identity → L3 root cause
    check: look for explicit Deny and Condition blocks (sourceVpc/sourceIp)
    on_clean: continue to L4

  - id: step_4
    action: check_scp_and_boundary
    tool: aws_org_console
    signal: SCP attached to account/OU; permission boundary on role
    gate: IF SCP blocks action → escalate to org admin (#MANUAL)
    on_clean: L4 ruled out

  - id: step_5
    action: check_network_condition
    tool: aws_cli
    command: "aws ec2 describe-instances --filters Name=private-ip-address,Values=<agent-ip>"
    signal: is the agent's VPC/IP in the allowed Condition set?
    gate: IF outside allowed VPC → fix Condition or move agent (#MANUAL)

human_gates:
  - any IAM policy modification
  - any resource policy modification
  - SCP changes (org admin required)
  - VPC endpoint policy changes
```

---

## Verifier Checklist

Before closing as resolved:

- [ ] `aws sts get-caller-identity` confirmed — identity is what was expected
- [ ] The specific action (e.g. s3:PutObject) appears in an Allow statement with no overriding Deny
- [ ] No explicit Deny in resource policy matching this identity/action
- [ ] No SCP blocking this action for the account
- [ ] If network Condition exists: agent is running in allowed VPC/IP range
- [ ] Reproduced success: the original operation works after fix

---

## Blast Radius

```
action_surface:  read-only for all diagnostic steps (list/get/simulate)
human_gates:     any policy modification (IAM, resource, SCP, boundary)
escalation:      SCP changes require org admin access — escalate, don't guess
caution:         adding wildcard (*) permissions to fix quickly = security incident risk
```

---

## Pattern Cross-Reference

```
cluster_rule:
  "In Cluster 5, always walk L1→L4 in order.
   99% of issues are at L2 (IAM policy).
   But 'explicit deny' and 'works in dev not prod' are L3/L4 patterns.
   Never add star permissions as a quick fix — always locate the specific missing action."

anti_pattern:
  Adding s3:* or * to fix an access denied = security violation.
  Always find the exact missing action first, then grant only that.
```
