I'll audit each PDB configuration for upgrade safety. Here's the analysis:

## 🚨 **BLOCKING CONFIGURATIONS (Will Prevent Upgrades)**

### Service A: `minAvailable=100%`
```yaml
# RISKY - Will block upgrades
spec:
  minAvailable: 100%
```
**Risk**: **HIGH** - This will completely block rolling updates since no pods can ever be unavailable.

### Service B: `maxUnavailable=0`
```yaml
# RISKY - Will block upgrades  
spec:
  maxUnavailable: 0
```
**Risk**: **HIGH** - Identical effect to 100% availability requirement.

## ✅ **SAFE CONFIGURATIONS**

### Service C: `minAvailable=2` (3 replicas)
```yaml
# SAFE - Allows 1 pod to be unavailable
spec:
  minAvailable: 2
```
**Risk**: **LOW** - Allows rolling updates while maintaining 2/3 pods available.

### Service D: `maxUnavailable=1` (5 replicas)
```yaml
# SAFE - Allows 1 pod to be unavailable
spec:
  maxUnavailable: 1
```
**Risk**: **LOW** - Maintains 4/5 pods during upgrades.

## 🔧 **Recommended Fixes**

### For Service A:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 80%  # or maxUnavailable: 20%
  selector:
    matchLabels:
      app: service-a
```

### For Service B:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # Allow 1 pod to be unavailable
  selector:
    matchLabels:
      app: service-b
```

## 📊 **Safe PDB Guidelines**

| Replicas | Safe minAvailable | Safe maxUnavailable | Availability During Upgrade |
|----------|-------------------|---------------------|----------------------------|
| 3        | 2 or 66%         | 1 or 33%           | 66% minimum |
| 5        | 3-4 or 60-80%    | 1-2 or 20-40%      | 60-80% minimum |
| 10       | 7-8 or 70-80%    | 2-3 or 20-30%      | 70-80% minimum |

## 🎯 **Best Practices**

1. **Never use 100% availability** for services with rolling updates
2. **Always allow at least 1 pod** to be unavailable for small deployments
3. **Test your PDBs** with drain simulations:
   ```bash
   kubectl drain <node> --dry-run=server
   ```
4. **Monitor during upgrades** to ensure PDBs aren't causing delays

**Summary**: Services A & B will block upgrades and need immediate attention. Services C & D are properly configured for safe upgrades.