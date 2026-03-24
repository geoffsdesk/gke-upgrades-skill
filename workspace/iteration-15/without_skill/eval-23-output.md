I'll audit each PDB configuration for upgrade safety. Here's my analysis:

## 🚨 **RISKY - Will Block Upgrades**

### Service A: `minAvailable=100%`
```yaml
# PROBLEMATIC - Blocks all disruptions
spec:
  minAvailable: 100%
```
**Risk**: Prevents ANY pod from being terminated during upgrades
**Fix**: Change to allow at least 1 disruption

### Service B: `maxUnavailable=0`
```yaml
# PROBLEMATIC - Same effect as 100% available
spec:
  maxUnavailable: 0
```
**Risk**: Identical issue - no pods can be disrupted
**Fix**: Allow at least 1 unavailable pod

## ✅ **SAFE - Allows Upgrades**

### Service C: `minAvailable=2` (3 replicas)
```yaml
# SAFE - Allows 1 pod disruption
spec:
  minAvailable: 2
```
**Analysis**: 67% availability maintained, 1 pod can be upgraded at a time

### Service D: `maxUnavailable=1` (5 replicas)
```yaml
# SAFE - Allows 1 pod disruption  
spec:
  maxUnavailable: 1
```
**Analysis**: 80% availability maintained, rolling upgrades will work

## 🔧 **Recommended Fixes**

```yaml
# Service A - Fixed
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 80%  # or maxUnavailable: 1
  selector:
    matchLabels:
      app: service-a

---
# Service B - Fixed
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # Allow 1 pod to be disrupted
  selector:
    matchLabels:
      app: service-b
```

## 📊 **Quick Test Command**

Test if upgrades will work:
```bash
# Check current PDB status
kubectl get pdb

# Simulate disruption (dry-run)
kubectl drain <node> --dry-run=client --ignore-daemonsets
```

**Bottom line**: Services A & B will definitely block upgrades and need immediate fixes. Services C & D are properly configured for safe rolling upgrades.