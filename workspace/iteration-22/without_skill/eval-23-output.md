I'll audit each PDB configuration for upgrade safety. Here's the breakdown:

## 🚨 **RISKY - Will Block Upgrades**

### Service A: `minAvailable=100%`
- **Risk**: HIGH - Will completely block rolling updates
- **Problem**: Kubernetes can never take down any pod, making updates impossible
- **Fix**: Change to `maxUnavailable=1` or `minAvailable=n-1` replicas

### Service B: `maxUnavailable=0`
- **Risk**: HIGH - Identical issue to Service A
- **Problem**: Zero pods can be unavailable = no updates possible
- **Fix**: Change to `maxUnavailable=1` or allow at least one pod disruption

## ✅ **SAFE - Upgrade Friendly**

### Service C: `minAvailable=2` (3 replicas)
- **Status**: SAFE
- **Why**: Allows 1 pod to be disrupted (3-2=1), enabling rolling updates
- **Maintains**: 66% availability during updates

### Service D: `maxUnavailable=1` (5 replicas)
- **Status**: SAFE  
- **Why**: Allows 1 pod disruption while maintaining 4/5 pods
- **Maintains**: 80% availability during updates

## 📋 **Recommended Fixes**

```yaml
# Service A - Fixed
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  maxUnavailable: 1  # Allow rolling updates
  selector:
    matchLabels:
      app: service-a

# Service B - Fixed  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # Allow rolling updates
  selector:
    matchLabels:
      app: service-b
```

## 🎯 **Best Practices Going Forward**

1. **Always allow ≥1 pod disruption** for rolling updates
2. **Use `maxUnavailable: 1`** as a safe default for most services
3. **Test PDBs** with `kubectl drain` before production
4. **Monitor during upgrades** to ensure PDBs aren't causing delays

**Bottom line**: Services A & B will definitely block your upgrades and need immediate fixes. Services C & D are properly configured.