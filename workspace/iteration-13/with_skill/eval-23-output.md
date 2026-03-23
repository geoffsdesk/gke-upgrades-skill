# PDB Audit for GKE Upgrade Safety

Based on your configurations, here's the upgrade risk assessment and recommendations:

## Current PDB Analysis

| Service | Configuration | Replicas | Upgrade Risk | Assessment |
|---------|---------------|----------|--------------|------------|
| **Service A** | `minAvailable=100%` | ? | 🔴 **BLOCKS UPGRADES** | Zero disruption allowed - will prevent node drain |
| **Service B** | `maxUnavailable=0` | ? | 🔴 **BLOCKS UPGRADES** | Same as 100% available - zero disruption allowed |
| **Service C** | `minAvailable=2` (3 replicas) | 3 | 🟡 **RISKY** | Only 1 pod can be disrupted - may cause issues |
| **Service D** | `maxUnavailable=1` (5 replicas) | 5 | 🟢 **SAFE** | Allows 1 disruption, keeps 4/5 running |

## Critical Issues

### Service A & B: Complete Upgrade Blockers
```yaml
# These configurations WILL block upgrades:
minAvailable: 100%  # Service A
maxUnavailable: 0   # Service B - equivalent to 100% available
```

**Problem:** GKE cannot drain any node containing these pods. During surge upgrades, GKE respects PDBs for up to 1 hour, then may force-delete pods.

**Impact:** Upgrade stalls, potential forced pod termination after timeout.

### Service C: Single Point of Failure
```yaml
minAvailable: 2  # With 3 replicas = maxUnavailable: 1
```

**Problem:** If 2 pods happen to be on the same node being drained, the upgrade blocks.

## Recommended Configurations

```yaml
# Service A - Allow some disruption
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 80%  # or maxUnavailable: 20%
  selector:
    matchLabels:
      app: service-a

# Service B - Same fix
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # Allow 1 pod disruption
  selector:
    matchLabels:
      app: service-b

# Service C - Increase replicas or allow more disruption
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-c-pdb
spec:
  minAvailable: 1    # Allow 2 disruptions instead of 1
  # OR scale to 5 replicas and keep minAvailable: 2
  selector:
    matchLabels:
      app: service-c

# Service D - Already good, no changes needed
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-d-pdb
spec:
  maxUnavailable: 1  # ✅ Safe configuration
  selector:
    matchLabels:
      app: service-d
```

## Upgrade-Safe PDB Principles

### 1. **Never use 100% availability**
```yaml
# ❌ AVOID - blocks all upgrades
minAvailable: 100%
maxUnavailable: 0

# ✅ PREFER - allows controlled disruption
minAvailable: 80%
maxUnavailable: 20%
```

### 2. **Account for multi-pod nodes**
If pods can be scheduled on the same node, ensure PDB allows multiple disruptions:
```yaml
# For 3 replicas that might co-locate:
minAvailable: 1        # Allows 2 disruptions
maxUnavailable: 2      # Same effect

# Or better: scale to 5+ replicas with anti-affinity
```

### 3. **Use percentage-based for large deployments**
```yaml
# Scales with replica count
minAvailable: 75%      # Always allows 25% disruption
maxUnavailable: 25%    # Same effect
```

## Pre-Upgrade PDB Check Command

```bash
#!/bin/bash
echo "=== PDB Upgrade Safety Audit ==="
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,CURRENT-HEALTHY:.status.currentHealthy,DESIRED-HEALTHY:.status.desiredHealthy,DISRUPTIONS-ALLOWED:.status.disruptionsAllowed"

echo -e "\n=== Risky PDBs (0 disruptions allowed) ==="
kubectl get pdb -A -o json | jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name) - \(.status.disruptionsAllowed) disruptions allowed"'
```

## Emergency PDB Bypass (If Upgrade Stucks)

If your upgrade gets stuck due to restrictive PDBs:

```bash
# 1. Identify blocking PDBs
kubectl get pdb -A -o wide | grep "0.*0"

# 2. Temporarily relax the most restrictive ones
kubectl patch pdb SERVICE-A-PDB -n NAMESPACE \
  -p '{"spec":{"minAvailable":"80%"}}'

# 3. Monitor upgrade progress
kubectl get nodes -w

# 4. Restore original PDB after upgrade
kubectl apply -f original-pdb-backup.yaml
```

## Action Items

1. **Immediate:** Fix Service A and B PDBs - they will definitely block upgrades
2. **Consider:** Scale Service C to 5+ replicas or reduce `minAvailable` to 1
3. **Validate:** Run the PDB check command before your next upgrade
4. **Test:** Validate PDB behavior in staging with a test upgrade

Your Service D configuration is already upgrade-safe and follows best practices. The key insight: PDBs should protect against failures, not prevent maintenance. Allowing 10-25% disruption typically provides both protection and upgrade flexibility.