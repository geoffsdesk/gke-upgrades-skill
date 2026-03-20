# PDB Audit for GKE Upgrade Safety

## Current PDB Analysis

| Service | Configuration | Replicas | Status | Risk Level | Impact on Upgrades |
|---------|---------------|----------|---------|------------|-------------------|
| **Service A** | `minAvailable=100%` | ? | ❌ **BLOCKS UPGRADES** | 🔴 **HIGH** | Will prevent any pod eviction during node drain |
| **Service B** | `maxUnavailable=0` | ? | ❌ **BLOCKS UPGRADES** | 🔴 **HIGH** | Identical to 100% minAvailable - no disruptions allowed |
| **Service C** | `minAvailable=2` (3 replicas) | 3 | ❌ **BLOCKS UPGRADES** | 🔴 **HIGH** | Can only lose 1 pod, but surge upgrade needs to drain nodes |
| **Service D** | `maxUnavailable=1` (5 replicas) | 5 | ✅ **UPGRADE SAFE** | 🟢 **LOW** | Allows 1 pod disruption while maintaining 4 healthy |

## Detailed Assessment

### Service A & B - Critical Issues
Both configurations are **functionally identical** and will block upgrades:
- `minAvailable=100%` = no pods can be unavailable
- `maxUnavailable=0` = no pods can be unavailable

**Problem:** During node drain, GKE needs to evict pods to upgrade the underlying node. These PDBs prevent any eviction.

### Service C - Edge Case Problem
With 3 replicas and `minAvailable=2`:
- Allows disruption of 1 pod maximum
- **Risky scenario:** If 1 pod is already unhealthy (CrashLoopBackOff, resource issues), the PDB effectively becomes `maxUnavailable=0`
- During upgrade, healthy pods can't be evicted because it would violate the 2-pod minimum

### Service D - Properly Configured
This is the **recommended pattern**:
- 5 replicas with `maxUnavailable=1` 
- Maintains 4 healthy pods during disruptions
- Provides both service continuity AND upgrade flexibility

## Recommended Fixes

### Quick Fix for Immediate Upgrade
```bash
# Temporarily relax overly restrictive PDBs
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":null,"maxUnavailable":"50%"}}'
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":"50%"}}'
kubectl patch pdb service-c-pdb -p '{"spec":{"minAvailable":"66%","maxUnavailable":null}}'

# After upgrade, restore if needed
```

### Long-term PDB Best Practices

**For critical services (need high availability):**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-service-pdb
spec:
  maxUnavailable: 1  # Always allow at least 1 pod disruption
  selector:
    matchLabels:
      app: critical-service
```

**For highly replicated services (≥5 replicas):**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-service-pdb
spec:
  maxUnavailable: 25%  # Percentage-based for scaling flexibility
  selector:
    matchLabels:
      app: web-service
```

**For small services (2-3 replicas):**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: small-service-pdb
spec:
  maxUnavailable: 1  # Absolute number, allows disruption
  selector:
    matchLabels:
      app: small-service
```

## PDB Guidelines for Upgrades

### ✅ Upgrade-Safe Patterns
- `maxUnavailable: 1` (any replica count ≥2)
- `maxUnavailable: "25%"` (for larger deployments)
- `minAvailable: "75%"` (leaves room for disruption)

### ❌ Upgrade-Blocking Patterns
- `minAvailable: 100%`
- `maxUnavailable: 0`
- `minAvailable: N` where N equals replica count
- `minAvailable: N` where N = replicas - 1 (too restrictive)

### 🟡 Context-Dependent (Risky)
- `minAvailable: "90%"` (depends on replica count)
- Very low replica counts (1-2) with any PDB

## Impact During GKE Upgrades

**What happens with blocking PDBs:**
1. GKE tries to drain a node
2. Pod eviction is attempted
3. PDB blocks the eviction
4. **GKE waits up to 1 hour** respecting the PDB
5. After 1 hour, GKE may force-drain (depending on cluster configuration)
6. Upgrade appears "stuck" during this waiting period

**Monitoring during upgrades:**
```bash
# Check which PDBs are blocking
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Monitor upgrade progress
kubectl get events --field-selector reason=EvictionBlocked
```

## Pre-Upgrade PDB Checklist

```markdown
- [ ] All PDBs allow at least 1 pod disruption (`maxUnavailable ≥ 1` or `minAvailable < 100%`)
- [ ] No `minAvailable=100%` or `maxUnavailable=0` configurations
- [ ] PDBs tested with replica scaling (ensure they don't become blocking at different scales)
- [ ] Non-critical services have relaxed PDBs (`maxUnavailable: "50%"` or higher)
- [ ] Database/stateful workloads have conservative but non-blocking PDBs (`maxUnavailable: 1`)
- [ ] PDB backup plan: commands ready to temporarily relax restrictive PDBs if upgrade stalls
```

**Bottom line:** Services A, B, and C will block your upgrade. Service D is configured correctly. Fix A/B/C before upgrading, or be prepared to relax them temporarily when the upgrade stalls.