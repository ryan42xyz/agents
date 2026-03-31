---
metadata:
  kind: runbook
  status: final
  summary: "A unified troubleshooting model for AWS access failures: work through four layers in order - who the identity is, what permissions it has (IAM policy), whether the resource allows it (resource policy), and whether a higher layer blocks it (SCP/boundary/endpoint). Includes CLI and console check paths, applicable to IAM/AMI/S3/KMS permission oncall and postmortems."
  tags: ["aws", "iam", "permissions", "access-denied"]
  first_action: "Run `aws sts get-caller-identity`"
---

---
Below is the **unified troubleshooting model for AWS permissions/AMI/resource access failures**.
Keep only the core logic chain and follow it in order.

## Trigger / Symptoms

- `AccessDenied` / `UnauthorizedOperation` / `is not authorized to perform` / `403`
- Can do A but not B (common: can `get` but cannot `list`)
- Works in dev but fails in prod (common: SCP/resource policy/endpoint policy)

Remember:

> Any AWS access failure boils down to 4 layers.

---

# 1. AWS access failure: the 4-layer model (general)

| Layer | What to check | Where to check |
| ----------- | ------------------------- | ----------- |
| 1. Who is the identity | Which role/user is currently in use | EC2/CLI |
| 2. What permissions the identity has | IAM policy | IAM console |
| 3. Whether the resource allows this identity | Resource policy | S3/AMI/KMS |
| 4. Whether blocked by a higher layer | SCP / boundary / endpoint | Org / VPC |

**99% of issues are in layer 2.**

---

# 2. Always confirm identity first (most important)

On the instance or locally:

```bash
aws sts get-caller-identity
```

Confirm the ARN looks like:

```text
assumed-role/xxx
```

If you skip this step,
everything after will be wrong.

---

# 3. Go to AWS UI and check permissions (core path)

Navigate to:

```text
IAM -> Roles -> find the current role
```

Only look at two things:

| What | Where |
| --------------- | ------------- |
| policy attached | Permissions   |
| policy contents | click policy JSON |

---

# 4. When reading a policy, do only one thing

Do not read everything.
Only look for:

```text
Is the Action allowed?
Does the Resource match?
```

Use this table to classify:

| Error type | Symptom |
| ----------- | ------------ |
| Action missing | Denied outright |
| Resource does not match | Looks allowed but still denied |
| Only object/* | Cannot list |
| Only bucket | Cannot get |

---

# 5. S3 quick decision table

If the error is for S3:

Ask yourself first:

```text
Is it failing to read an object?
Or failing to list (ls)?
```

| Symptom | Likely cause |
| ----------- | --------------- |
| Can cp but cannot ls | Missing bucket-level permissions |
| Nothing works | Role has no permissions |
| Only one bucket fails | Resource does not match |
| Suddenly everything fails | SCP or bucket deny |

---

# 6. bucket-level vs object-level (must know)

| Operation | Requires |
| --------- | ------------ |
| aws s3 ls | bucket ARN   |
| get/put   | bucket/* ARN |

Must be paired:

```text
arn:aws:s3:::bucket
arn:aws:s3:::bucket/*
```

Missing either one will cause problems.

---

# 7. If IAM looks fine

Then check the resource policy:

### S3

```text
S3 → bucket → permissions → bucket policy
```

### AMI

```text
EC2 → AMI → launch permissions
```

### KMS

```text
KMS → key policy
```

Only look for:

```text
Deny
or your role is not allowed
```

---

# 8. If everything still looks fine

Check org-level blocking:

```text
AWS Organizations → SCP
```

Or:

```text
VPC endpoint policy
```

This layer is less common,
but shows up in larger orgs.

---

# 9. AMI permission issues: dedicated model

For AMI launch failures, only check three things:

| Layer | What to check |
| ----------- | ----------------- |
| Is the AMI shared | AMI -> permissions |
| AMI region | Must be the same region |
| Is KMS allowed | Encrypted AMI requires the key policy to allow it |

80% of AMI failures are because it is not shared, or KMS denies it.

---

# 10. The core troubleshooting mental model

For any AWS permission error in the future:

Ask yourself these four questions first:

1. Who am I right now (which role)
2. Does this role allow the Action
3. Does the Resource ARN match
4. Is there a higher-level deny

Follow this order.
Do not skip steps.

---

# 11. Fastest practical path (memorize this)

Doing only this is usually enough:

```text
1. aws sts get-caller-identity
2. IAM -> find the role
3. Read policy JSON
4. Check whether Resource matches
```

Do not start by blaming AWS.
99% of the time the resource does not match.

---

### The minimal model for AWS permission errors

**All AccessDenied errors come from only 4 layers:**

| Layer | Who controls it | Share |
| ----------------- | ------------- | --- |
| IAM role policy | Identity permissions | 80% |
| Resource policy | S3/AMI/KMS resource side | 15% |
| SCP (org) | Account-level ceiling | <5% |
| Boundary/endpoint | Additional enterprise security layer | rare |

---

# 12. Decide early whether it is SCP (most important)

Only check SCP when you see signals like these:

| Signal | Meaning |
| --------------- | -------- |
| Even admin fails | Not IAM |
| All roles fail | Not a single role issue |
| Same action works in dev but not prod | Account-level restriction |
| Fails across all regions | Common SCP pattern |
| Uniform failure to create resources | e.g. EC2/KMS |

One-liner:

> If even admins cannot do it, it is 100% SCP.

---

# 13. Typical cases that are not SCP

If you see these, it is **definitely not SCP**:

| Symptom | Likely cause |
| ---------- | --------------- |
| Only one role fails | IAM policy |
| Can read but cannot list | Missing bucket-level permissions |
| Only one bucket fails | Resource policy |
| Works after switching role | IAM |

---

## Decision / action boundaries

- Prove which permission is missing and which layer is denying before changing policy; do not add `*` permissions by intuition.
- Production policy changes are write actions: follow human review/change process (minimize scope and ensure rollback).

## Verify

- Use `aws sts get-caller-identity` to confirm the identity matches expectation.
- Re-run the original failing command: confirm `AccessDenied` becomes success (or the error changes in an expected way).

## Exit criteria

- You have pinpointed the single responsible layer (IAM / Resource policy / SCP / Boundary/endpoint).
- You provided an actionable remediation recommendation (least privilege) and verified it.

SCP will not block only one role.

It blocks:

> the entire account

---

# 14. AWS UI check path (remember only this)

```text
AWS Organizations
→ Accounts
→ target account
→ Policies
→ Service Control Policies
```

Only look for:

```json
"Effect": "Deny"
```

---

# 15. IAM vs SCP: the key difference (one sentence)

IAM:

> what you are allowed to do

SCP:

> the maximum you are allowed to do

SCP is an account-level ceiling.
IAM cannot exceed it.

---

# 16. Practical decision order (always follow this)

When you see AccessDenied:

```text
1. Confirm current role (sts)
2. Check IAM policy
3. Check resource policy
4. Only if both allow -> check SCP
```

Do not start by checking SCP.
But if:

> everything looks correct but you are still denied

go check the org layer.

---

# 17. Engineer-level reflexes

| Feeling | Reality |
| ------------------- | ----------------- |
| Only my machine fails | IAM |
| The whole account fails | SCP |
| Different behavior across accounts in the same company | SCP |
| Policy says allow but still denied | SCP or resource deny |

---

# The single most important sentence

> IAM decides whether you can do it.
> SCP decides whether the company allows anyone to do it.

---
