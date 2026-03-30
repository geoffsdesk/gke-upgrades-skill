# PDB Upgrade Risk Assessment

I'll analyze each PDB configuration for upgrade safety. The key principle: **PDBs must allow at least 1 pod disruption during node drain**, or GKE will respect them for up to 1 hour, then force-evict.

## Risk Analysis

### ⚠️ HIGH RISK - Will Block Upgrades

**Service A: `minAvailable=100%`**
- **Problem**: Never allows ANY pod disruption
- **Impact**: Blocks all node drains indefinitely until 1-hour timeout, then force-eviction
- **Fix**: Change to `minAvailable=50%` or `maxUnavailable=1`

**Service B: `maxUnavailable=0`** 
- **Problem**: Identical to 100% available - no disruptions allowed
- **Impact**: Same blocking behavior as Service A
- **Fix**: Change to `maxUnavailable=1` or `minAvailable="50%"`

### ✅ LOW RISK - Upgrade Safe

**Service C: `minAvailable=2` with 3 replicas**
- **Analysis**: Allows 1 pod disruption (3 - 2 = 1 unavailable)
- **Upgrade behavior**: Smooth rolling drain, maintains 2-pod service availability
- **Recommendation**: Keep as-is ✓

**Service D: `maxUnavailable=1` with 5 replicas**
- **Analysis**: Explicitly allows 1 pod disruption, maintains 4 pods
- **Upgrade behavior**: Optimal for upgrades while preserving high availability
- **Recommendation**: Keep as-is ✓

## Recommended PDB Fixes

```yaml
# Service A - BEFORE (blocks upgrades)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 100%  # ❌ NEVER allows disruption
  selector:
    matchLabels:
      app: service-a

# Service A - AFTER (upgrade-safe)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  maxUnavailable: 1   # ✅ Allows 1 disruption
  selector:
    matchLabels:
      app: service-a
```

```yaml
# Service B - BEFORE (blocks upgrades)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 0   # ❌ Same as minAvailable=100%
  selector:
    matchLabels:
      app: service-b

# Service B - AFTER (upgrade-safe)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1   # ✅ Allows 1 disruption
  selector:
    matchLabels:
      app: service-b
```

## Implementation Commands

**Check current PDB status before upgrade:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0 (these will block)
```

**Apply the fixes:**
```bash
# Update Service A PDB
kubectl patch pdb service-a-pdb \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":1}}'

# Update Service B PDB  
kubectl patch pdb service-b-pdb \
  -p '{"spec":{"maxUnavailable":1}}'

# Verify changes
kubectl get pdb -A -o wide
# Confirm ALLOWED DISRUPTIONS > 0 for all PDBs
```

## Monitoring During Upgrades

**Set up PDB violation monitoring:**
```bash
# Monitor for PDB blocking events in Cloud Logging
gcloud logging read 'resource.type="gke_cluster" jsonPayload.reason="EvictionBlocked"' \
  --project=PROJECT_ID \
  --freshness=1h
```

**Watch for GKE disruption events:**
- `POD_PDB_VIOLATION`: Eviction blocked by PDB
- `POD_NOT_ENOUGH_PDB`: Insufficient replicas for PDB
- PDB timeout: Force-eviction after 1 hour

## Best Practices Summary

✅ **Good PDB patterns for upgrades:**
- `maxUnavailable: 1` (explicit disruption allowance)
- `minAvailable: "50%"` (percentage-based)
- `minAvailable: N-1` where N = replica count

❌ **Bad PDB patterns for upgrades:**
- `minAvailable: 100%` (never allows disruption)
- `maxUnavailable: 0` (same effect)
- `minAvailable: N` where N = replica count (no disruption room)

Your **Services C and D are already upgrade-safe**. Fix Services A and B with the commands above, and you'll have smooth upgrades while maintaining service availability.