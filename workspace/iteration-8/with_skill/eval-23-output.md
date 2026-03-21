# PDB Audit for GKE Upgrade Safety

## Risk Assessment Summary

| Service | Current PDB | Risk Level | Upgrade Impact |
|---------|-------------|------------|----------------|
| **Service A** | `minAvailable=100%` | 🔴 **HIGH RISK** | **WILL BLOCK** upgrades |
| **Service B** | `maxUnavailable=0` | 🔴 **HIGH RISK** | **WILL BLOCK** upgrades |
| **Service C** | `minAvailable=2` (3 replicas) | 🔴 **HIGH RISK** | **WILL BLOCK** upgrades |
| **Service D** | `maxUnavailable=1` (5 replicas) | 🟢 **SAFE** | Allows disruption |

## Detailed Analysis

### Service A: `minAvailable=100%` ❌
**Problem:** Requires ALL pods to remain available at all times. During node upgrades, GKE must drain nodes, which means temporarily reducing available replicas.

**Impact:** GKE cannot evict any pods from this service, blocking the upgrade entirely.

**Fix:** Change to `minAvailable=80%` or `maxUnavailable=1` to allow some disruption.

### Service B: `maxUnavailable=0` ❌
**Problem:** Identical to 100% availability requirement. Zero pods can be unavailable simultaneously.

**Impact:** Upgrade will stall when trying to drain nodes running these pods.

**Fix:** Allow at least 1 pod disruption: `maxUnavailable=1` or `minAvailable="80%"`.

### Service C: `minAvailable=2` with 3 replicas ❌
**Problem:** With only 3 replicas total, requiring 2 to remain available means only 1 can be disrupted. However, if 2+ pods are on the same node being drained, the PDB blocks eviction.

**Impact:** High risk of blocking upgrades, especially in smaller clusters where pod distribution is less predictable.

**Fix:** Either increase replicas to 5+ or change to `maxUnavailable=1`.

### Service D: `maxUnavailable=1` with 5 replicas ✅
**Problem:** None - this is properly configured.

**Why it works:** Allows 1 pod to be disrupted while keeping 4 available, giving GKE flexibility to drain nodes.

## Recommended PDB Configuration

```yaml
# Service A - FIXED
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  maxUnavailable: 1  # Or minAvailable: 80%
  selector:
    matchLabels:
      app: service-a

# Service B - FIXED  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: service-b

# Service C - FIXED (option 1: allow more disruption)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-c-pdb
spec:
  maxUnavailable: 1  # Instead of minAvailable=2
  selector:
    matchLabels:
      app: service-c

# Service D - ALREADY GOOD
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-d-pdb
spec:
  maxUnavailable: 1  # Keep as-is
  selector:
    matchLabels:
      app: service-d
```

## Alternative Fix for Service C

If Service C truly needs high availability, increase replicas instead of relaxing the PDB:

```yaml
# Option 2: Scale up replicas
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-c
spec:
  replicas: 5  # Increase from 3
  # ... rest of spec

---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-c-pdb
spec:
  minAvailable: 3  # Now allows 2 disruptions with 5 replicas
  selector:
    matchLabels:
      app: service-c
```

## General PDB Best Practices for GKE Upgrades

### ✅ Upgrade-Safe Patterns
- **`maxUnavailable=1`** - Simple and safe for most services
- **`minAvailable="80%"`** - Percentage-based, scales with replicas
- **`minAvailable=N-1`** where N is replica count ≥ 3

### ❌ Upgrade-Blocking Patterns
- **`minAvailable=100%`** or **`maxUnavailable=0`** - Never allow disruption
- **`minAvailable=replicas-1`** with low replica counts (2-3 total)
- **No PDB at all** for critical services (bare pods get force-deleted)

### 🔧 Node Pool Strategy Considerations

For your upgrade strategy, since you have restrictive PDBs:

```bash
# Use conservative surge settings to avoid resource pressure
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This creates replacement nodes before draining, giving your workloads somewhere to reschedule.

## Pre-Upgrade Testing

Before your upgrade, test the PDB changes:

```bash
# Check current PDB status
kubectl get pdb -A -o wide

# Simulate eviction (doesn't actually evict)
kubectl get pods -l app=service-a -o name | head -1 | \
  xargs kubectl delete --dry-run=server

# Monitor during upgrade
kubectl get pdb -A --watch
```

## Upgrade Monitoring Commands

During your upgrade, watch for PDB blocks:

```bash
# Check for pods blocked by PDBs
kubectl get events -A --field-selector reason=EvictionBlocked

# Monitor PDB disruption allowances  
kubectl get pdb -A -o custom-columns="NAME:.metadata.name,NAMESPACE:.metadata.namespace,MIN AVAILABLE:.spec.minAvailable,MAX UNAVAILABLE:.spec.maxUnavailable,ALLOWED DISRUPTIONS:.status.disruptionsAllowed"
```

**Summary:** Your current PDB configuration will likely block GKE upgrades. Services A, B, and C need immediate fixes before attempting any cluster upgrades. Service D is properly configured.