# PDB Audit for GKE Upgrade Safety

Based on your configuration, here's the upgrade risk assessment and recommendations:

## Risk Assessment

| Service | Current PDB | Replicas | Upgrade Risk | Assessment |
|---------|-------------|----------|--------------|------------|
| **Service A** | `minAvailable=100%` | Unknown | 🔴 **HIGH RISK** | Will block all node drains |
| **Service B** | `maxUnavailable=0` | Unknown | 🔴 **HIGH RISK** | Will block all node drains |
| **Service C** | `minAvailable=2` | 3 | 🟡 **MEDIUM RISK** | Allows 1 disruption, may work |
| **Service D** | `maxUnavailable=1` | 5 | 🟢 **LOW RISK** | Safe for upgrades |

## Detailed Analysis

### Service A & B - WILL BLOCK UPGRADES
```yaml
# Service A: minAvailable=100%
# Service B: maxUnavailable=0
# Both configurations prevent ANY pod disruption
```

**Problem:** During surge upgrades, GKE needs to drain nodes. These PDBs prevent any pod eviction, causing the upgrade to hang indefinitely.

**Immediate fix for upgrade:**
```bash
# Temporarily relax Service A
kubectl patch pdb service-a-pdb -n NAMESPACE \
  -p '{"spec":{"minAvailable":"80%","maxUnavailable":null}}'

# Temporarily relax Service B  
kubectl patch pdb service-b-pdb -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"20%"}}'
```

### Service C - BORDERLINE RISKY
```yaml
# minAvailable=2 with 3 replicas = maxUnavailable=1
```

**Analysis:** Mathematically allows 1 disruption, but risky because:
- If one replica is already unhealthy, PDB becomes `maxUnavailable=0`
- Rolling deployments consume the disruption budget
- Node upgrades compete with app deployments for the single allowed disruption

**Recommendation:** Increase replicas to 5+ for more disruption budget headroom.

### Service D - SAFE
```yaml
# maxUnavailable=1 with 5 replicas = minAvailable=4 (80%)
```

**Analysis:** ✅ Good configuration. Allows controlled disruption while maintaining service availability.

## Upgrade-Safe PDB Guidelines

### Recommended patterns by service criticality:

**Highly available services (user-facing):**
```yaml
spec:
  maxUnavailable: 25%  # Or 1-2 pods, whichever is larger
  # Allows gradual rolling but maintains majority
```

**Background services:**
```yaml
spec:
  maxUnavailable: 50%  # More aggressive, faster upgrades
```

**Single-replica services:**
```yaml
# No PDB - let them restart
# Or use maxUnavailable=1 with replicas ≥ 3
```

## Pre-Upgrade PDB Checklist

```bash
# 1. Audit all PDBs
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable"

# 2. Check actual disruption allowances
kubectl get pdb -A -o wide
# Look for "ALLOWED DISRUPTIONS" = 0

# 3. Test PDB math with current replica counts
for pdb in $(kubectl get pdb -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}'); do
  echo "=== $pdb ==="
  kubectl describe pdb $pdb
done
```

## Recommended Changes

### Service A & B (Critical Fix)
```yaml
# Replace 100% availability with reasonable threshold
apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  maxUnavailable: 20%  # Allows some disruption
  # OR minAvailable: 80% if you prefer that syntax
```

### Service C (Improvement)
```yaml
# Scale up first for better resilience
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 5  # Up from 3

---
apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  maxUnavailable: 2  # Allows 2 disruptions with 5 replicas
```

### Service D (Keep As-Is)
Your current configuration is already upgrade-safe. No changes needed.

## GKE Upgrade Behavior with PDBs

**Important details:**
- GKE respects PDBs for up to **1 hour** during node drains
- After 1 hour, GKE may force-drain nodes regardless of PDBs
- Surge upgrades create new nodes first, then drain old ones (safer than in-place)
- PDB violations during upgrades are temporary - pods reschedule to new nodes

## Quick Fix Script for Your Upgrade

```bash
#!/bin/bash
# Back up current PDBs
kubectl get pdb -A -o yaml > pdb-backup-$(date +%Y%m%d).yaml

# Relax restrictive PDBs temporarily
kubectl patch pdb service-a-pdb -n NAMESPACE -p '{"spec":{"minAvailable":"80%","maxUnavailable":null}}'
kubectl patch pdb service-b-pdb -n NAMESPACE -p '{"spec":{"minAvailable":null,"maxUnavailable":"20%"}}'

echo "PDBs relaxed for upgrade. Restore from backup after completion:"
echo "kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml"
```

**Bottom line:** Services A & B will definitely block your upgrade. Fix those before starting. Service C is borderline risky. Service D is fine as-is.