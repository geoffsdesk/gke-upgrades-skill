# PDB Audit for GKE Upgrade Safety

Based on your PDB configurations, here's the upgrade risk assessment and recommendations:

## Current Configuration Analysis

| Service | Configuration | Replicas | Assessment | Upgrade Risk |
|---------|---------------|----------|------------|--------------|
| **Service A** | `minAvailable=100%` | Unknown | ❌ **BLOCKS UPGRADES** | **HIGH** |
| **Service B** | `maxUnavailable=0` | Unknown | ❌ **BLOCKS UPGRADES** | **HIGH** |
| **Service C** | `minAvailable=2` (3 replicas) | 3 | ✅ **Safe** | **LOW** |
| **Service D** | `maxUnavailable=1` (5 replicas) | 5 | ✅ **Safe** | **LOW** |

## Detailed Analysis

### ❌ Service A: `minAvailable=100%` - UPGRADE BLOCKER
**Problem:** This prevents ANY pod from being evicted during node drain. GKE cannot drain nodes when 100% availability is required.

**Impact:** Node pool upgrades will stall completely. After 1 hour, GKE will force-evict pods anyway, potentially causing service disruption.

**Fix:**
```bash
# Allow 1 pod disruption for rolling upgrades
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"66%"}}'
# OR specify absolute number
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":2,"maxUnavailable":null}}'
```

### ❌ Service B: `maxUnavailable=0` - UPGRADE BLOCKER
**Problem:** Identical to Service A - no pods can be unavailable means no drain is possible.

**Impact:** Same as Service A - complete upgrade blockage.

**Fix:**
```bash
# Allow 1 pod disruption
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1,"minAvailable":null}}'
```

### ✅ Service C: `minAvailable=2` (3 replicas) - SAFE
**Analysis:** Allows 1 pod (33%) to be unavailable during drain. GKE can evict 1 pod at a time while maintaining 2 running pods.

**Recommendation:** This is well-configured for upgrades. No changes needed.

### ✅ Service D: `maxUnavailable=1` (5 replicas) - SAFE
**Analysis:** Allows 1 pod (20%) to be unavailable. Maintains 4 running pods during drain.

**Recommendation:** Conservative and safe. Consider allowing `maxUnavailable=2` if you can tolerate brief periods with 3 replicas during upgrades.

## Recommended PDB Patterns for Upgrade Safety

### For web services / APIs (stateless):
```yaml
spec:
  minAvailable: 66%  # or minAvailable: N-1 for small deployments
  # Allows 1/3 of pods to be unavailable during rolling updates
```

### For databases / stateful services:
```yaml
spec:
  maxUnavailable: 1
  # Conservative: only 1 replica unavailable at a time
```

### For high-throughput services:
```yaml
spec:
  minAvailable: 80%  # Maintains most capacity during upgrades
```

## Pre-Upgrade PDB Fixes

Apply these patches before your next upgrade:

```bash
# Service A - allow 33% unavailable (adjust based on actual replica count)
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"67%","maxUnavailable":null}}'

# Service B - allow 1 pod unavailable  
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1,"minAvailable":null}}'

# Services C & D - no changes needed (already safe)
```

## Monitoring During Upgrades

Monitor for PDB violations during your upgrade:

```bash
# Check current PDB status
kubectl get pdb -A -o wide

# Watch for eviction blocks in real-time
kubectl get events -A -w --field-selector reason=EvictionBlocked

# GKE-specific disruption events (Cloud Logging)
# Filter: resource.type="gke_cluster" jsonPayload.reason="POD_PDB_VIOLATION"
```

## GKE PDB Timeout Behavior

**Important:** GKE respects PDBs for up to **1 hour** during surge upgrades, then force-evicts remaining pods. If your PDB blocks drain:

1. **0-60 minutes:** GKE waits, respecting PDB
2. **After 60 minutes:** Force eviction with `terminationGracePeriodSeconds` capped at 60 minutes
3. **Notification:** GKE sends `POD_PDB_VIOLATION` events to Cloud Logging

## Quick Validation

Test your PDB settings before the real upgrade:

```bash
# Simulate drain (without actually draining)
kubectl drain NODE_NAME --dry-run=client --ignore-daemonsets --delete-emptydir-data

# Check which pods would be blocked
kubectl get pods -A -o wide --field-selector spec.nodeName=NODE_NAME
```

## Summary & Next Steps

1. **Immediate action required:** Fix Service A and B PDBs before your next upgrade
2. **Services C & D:** Already properly configured
3. **Test your changes:** Use the validation commands above
4. **Monitor during upgrade:** Watch for PDB violation events
5. **Document the pattern:** Use these PDB guidelines for future services

Your Services C and D show you understand PDB best practices. Apply the same pattern to Services A and B, and your upgrades should proceed smoothly without service disruption.