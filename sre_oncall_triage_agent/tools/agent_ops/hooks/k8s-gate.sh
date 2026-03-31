#!/bin/bash
# k8s-gate.sh — PreToolUse hook for K8s/AWS operation safety
# Environment tier enforcement: PROD/PCI/MGT/DEMO (read-only) > PREPROD (read + dry-run) > DEV (most permissive)
# Exit 0 = allow (still goes through normal permission flow)
# Exit 2 = hard block (Claude sees stderr as feedback)

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# ─── Alias classification ──────────────────────────────────────────────────────
# All kubectl aliases (by region prefix)
ALL_K_ALIASES="(kubectl|kafsouth|kwest|keast|keu|ksg[ab]|kasiasedcube|kgcpwest|kca[^p]|kcap)"

# Environment tier aliases
PCI_ALIASES="(keastpcia|keastpcib)"
PROD_ALIASES="(kafsouthproda|kafsouthprodb|kwestproda|kwestprodb|keastproda|keastprodb|keuwestproda|keuwestprodb|keuwest2prodb|ksga|ksgb|kasiasedcube|kgcpwestproda|kcaproda|kcaprodb)"
MGT_ALIASES="(kwestmgt|keastmgt)"
PREPROD_ALIASES="(kafsouthpreprod|kwestpreprod|keastpreprod|keastpcipreprod|kcapreprod)"
DEV_ALIASES="(kwestdeva|kwestdevb|keastdevc)"
DEMO_ALIASES="(kwestdemoa|kwestdemob|kgcpwestpoca|kgcpwestpocb|kgcpwesttrial)"

# Operation patterns
MUTATING_PAT=" (apply|create|scale|patch|rollout restart|drain|cordon|taint|exec|cp|run )"
DELETE_PAT=" (delete|del) "

# Not a K8s/AWS command — skip entirely
if ! echo "$CMD" | grep -qE "^($ALL_K_ALIASES|helm|aws|eksctl|k9s|kubectx|kubens)"; then
  exit 0
fi

ALIAS=$(echo "$CMD" | awk '{print $1}')

# ═══════════════════════════════════════════════════════════════════════════════
# HARD BLOCKS — all tiers
# ═══════════════════════════════════════════════════════════════════════════════

# Block: delete namespace on ANY cluster
if echo "$CMD" | grep -qE "^[^ ]+ (delete|del) (ns|namespace)\b"; then
  echo "[k8s-gate] BLOCKED: namespace deletion via agent is not allowed ($ALIAS). Run manually." >&2
  exit 2
fi

# Block: cross-namespace mass deletion
if echo "$CMD" | grep -qE "^[^ ]+ delete .*(--all-namespaces|-A\b)"; then
  echo "[k8s-gate] BLOCKED: cross-namespace deletion not allowed via agent." >&2
  exit 2
fi

# Block: IAM mutations
if echo "$CMD" | grep -qE "^aws iam (create|delete|attach|detach|put|add|remove|update)"; then
  echo "[k8s-gate] BLOCKED: IAM mutations not allowed via agent." >&2
  exit 2
fi

# Block: EC2 instance terminate/stop
if echo "$CMD" | grep -qE "^aws ec2 (terminate-instances|stop-instances)"; then
  echo "[k8s-gate] BLOCKED: EC2 instance termination/stop not allowed via agent." >&2
  exit 2
fi

# Block: network/DNS mutations
if echo "$CMD" | grep -qE "^aws (route53|ec2 (delete|revoke|authorize)-(security|vpc)|ec2 delete-vpc)"; then
  echo "[k8s-gate] BLOCKED: network/DNS mutations not allowed via agent." >&2
  exit 2
fi

# Block: --context prod (explicit context override)
if echo "$CMD" | grep -qE "\-\-context[= ](prod|production|prd)"; then
  echo "[k8s-gate] BLOCKED: explicit production context flag detected. Switch context manually." >&2
  exit 2
fi

# ═══════════════════════════════════════════════════════════════════════════════
# TIER: PROD / PCI / DEMO — read-only, ALL mutating ops blocked
# PCI and DEMO follow PROD policy (read allowed, mutating blocked)
# ═══════════════════════════════════════════════════════════════════════════════

if echo "$CMD" | grep -qE "^($PROD_ALIASES|$PCI_ALIASES|$DEMO_ALIASES)\b"; then
  if echo "$CMD" | grep -qE "$DELETE_PAT"; then
    echo "[k8s-gate] BLOCKED: delete on PROD/PCI/DEMO ($ALIAS) not allowed via agent." >&2
    exit 2
  fi

  if echo "$CMD" | grep -qE "$MUTATING_PAT"; then
    echo "[k8s-gate] BLOCKED: mutating op on PROD/PCI/DEMO ($ALIAS) not allowed via agent." >&2
    echo "[k8s-gate] Policy: read-only. Generate the command for human to run:" >&2
    echo "[k8s-gate] → $CMD" >&2
    exit 2
  fi
  # Read ops fall through to read-op resource protection below
fi

# ═══════════════════════════════════════════════════════════════════════════════
# TIER: MGT — read-only, same as PROD
# ═══════════════════════════════════════════════════════════════════════════════

if echo "$CMD" | grep -qE "^$MGT_ALIASES\b"; then
  if echo "$CMD" | grep -qE "$DELETE_PAT|$MUTATING_PAT"; then
    echo "[k8s-gate] BLOCKED: mutating op on MGT ($ALIAS) not allowed via agent. Generate command for human." >&2
    exit 2
  fi
  # Read ops fall through to read-op resource protection below
fi

# ═══════════════════════════════════════════════════════════════════════════════
# TIER: PREPROD — read + dry-run OK, real mutating ops need human approval
# ═══════════════════════════════════════════════════════════════════════════════

if echo "$CMD" | grep -qE "^$PREPROD_ALIASES\b"; then
  if echo "$CMD" | grep -qE "$DELETE_PAT"; then
    echo "[k8s-gate] BLOCKED: delete on PREPROD ($ALIAS) not allowed via agent." >&2
    exit 2
  fi

  if echo "$CMD" | grep -qE "$MUTATING_PAT"; then
    if echo "$CMD" | grep -q "\-\-dry-run"; then
      echo "[k8s-gate] PREPROD ($ALIAS): --dry-run detected, showing plan only." >&2
    else
      echo "[k8s-gate] WARNING: Mutating op on PREPROD ($ALIAS) without --dry-run." >&2
      echo "[k8s-gate] PREPROD policy: run --dry-run=client first, then get human approval." >&2
    fi

    if ! echo "$CMD" | grep -q "# INTENT:"; then
      echo "[k8s-gate] INTENT MISSING: Add '# INTENT: <reasoning>' before this command." >&2
    fi

    # Per-operation verify hint
    if echo "$CMD" | grep -qE " scale "; then
      RESOURCE=$(echo "$CMD" | grep -oE '(deploy|deployment|sts|statefulset)[/ ][^ ]+' | head -1)
      echo "[k8s-gate] VERIFY after: kubectl rollout status $RESOURCE && kubectl get $RESOURCE" >&2
    elif echo "$CMD" | grep -qE " (apply|create) "; then
      echo "[k8s-gate] VERIFY after: kubectl get <resource> to confirm Ready" >&2
    elif echo "$CMD" | grep -qE " (patch|rollout restart) "; then
      echo "[k8s-gate] VERIFY after: kubectl rollout status <resource> && kubectl get pods" >&2
    fi
  fi
  # Fall through to read-op resource protection below
fi

# ═══════════════════════════════════════════════════════════════════════════════
# TIER: DEV — most permissive
# ═══════════════════════════════════════════════════════════════════════════════

if echo "$CMD" | grep -qE "^$DEV_ALIASES\b"; then
  if echo "$CMD" | grep -qE "$DELETE_PAT"; then
    echo "[k8s-gate] WARNING: delete on DEV ($ALIAS). Confirm target resource." >&2
  fi

  if echo "$CMD" | grep -qE "$MUTATING_PAT" && ! echo "$CMD" | grep -q "\-\-dry-run"; then
    if ! echo "$CMD" | grep -q "# INTENT:"; then
      echo "[k8s-gate] INTENT MISSING: Add '# INTENT: <reasoning>' before this command." >&2
    fi
  fi
  # Fall through to read-op resource protection below
fi

# ═══════════════════════════════════════════════════════════════════════════════
# UNCLASSIFIED ALIAS — conservative default (treat as PROD)
# ═══════════════════════════════════════════════════════════════════════════════

if echo "$CMD" | grep -qE "^$ALL_K_ALIASES\b"; then
  if echo "$CMD" | grep -qE "$MUTATING_PAT|$DELETE_PAT"; then
    echo "[k8s-gate] BLOCKED: Unclassified alias ($ALIAS) — treating as PROD, mutating ops blocked." >&2
    echo "[k8s-gate] Add this alias to a tier in k8s-gate.sh if it should be less restricted." >&2
    exit 2
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# READ-OP RESOURCE PROTECTION — all tiers
# ═══════════════════════════════════════════════════════════════════════════════

# Warn: kubectl logs -f (long-running API server connection)
if echo "$CMD" | grep -qE " logs.*(-f\b|--follow)"; then
  echo "[k8s-gate] WARNING: 'kubectl logs -f' holds a persistent API server connection. Use --tail=<N> without -f when possible." >&2
fi

# Warn: all-namespace query (expensive on large clusters)
if echo "$CMD" | grep -qE " (get|describe) .*(--all-namespaces|-A\b)"; then
  echo "[k8s-gate] WARNING: all-namespace query may be slow on large clusters. Add -n <namespace> if possible." >&2
fi

# Notice: kubectl get without -n (uses default context namespace)
if echo "$CMD" | grep -qE " get " && ! echo "$CMD" | grep -qE "( -n |--namespace[= ])| -A |--all-namespaces"; then
  echo "[k8s-gate] NOTICE: kubectl get without -n <namespace>. Using default context namespace." >&2
fi

# ═══════════════════════════════════════════════════════════════════════════════
# HELM — tier-aware
# ═══════════════════════════════════════════════════════════════════════════════

if echo "$CMD" | grep -qE "^helm (upgrade|install)"; then
  if ! echo "$CMD" | grep -q "\-\-dry-run"; then
    RELEASE=$(echo "$CMD" | awk '{print $3}')
    echo "[k8s-gate] NOTICE: helm upgrade/install without --dry-run." >&2
    echo "[k8s-gate] VERIFY after: helm status $RELEASE && kubectl get pods -n <namespace>" >&2
  fi
fi

exit 0
