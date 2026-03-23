I'll audit each of your PDB configurations for upgrade safety. Here's my analysis:

## PDB Upgrade Safety Audit

### ⚠️ **RISKY - Will Block Upgrades**

**Service A: `minAvailable=100%`**
- **Risk Level:** HIGH - Will definitely block upgrades
- **Problem:** Requires ALL replicas to stay available at all times
- **Impact:** Node drain will fail because no pods can be evicted
- **Fix:** Change to `minAvailable=80%` or `maxUnavailable=1`

**Service B: `maxUnavailable=0`**
- **Risk Level:** HIGH - Will definitely block upgrades  
- **Problem:** Identical to 100% availability requirement
- **Impact:** No pods can be terminated during drain
- **Fix:** Change to `maxUnavailable=1` or `minAvailable` with reasonable percentage

### ✅ **SAFE - Upgrade Compatible**

**Service C: `minAvailable=2` with 3 replicas**
- **Risk Level:** LOW - Safe for upgrades
- **Analysis:** Allows 1 pod to be unavailable (3-2=1)
- **Behavior:** During drain, 1 pod can be evicted while 2 remain serving
- **Recommendation:** Keep as-is ✓

**Service D: `maxUnavailable=1` with 5 replicas**
- **Risk Level:** LOW - Safe for upgrades
- **Analysis:** Allows 1 pod down, keeps 4 serving (80% availability)
- **Behavior:** Node drain can proceed smoothly
- **Recommendation:** Keep as-is ✓

## Quick Fix Commands

```bash
# Fix Service A - allow 1 pod disruption
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":null,"maxUnavailable":"1"}}'

# Fix Service B - allow 1 pod disruption  
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":"1"}}'
```

## Recommended PDB Strategy

For upgrade-safe PDBs, follow this pattern:

```yaml
# Option 1: Percentage-based (recommended for larger deployments)
spec:
  minAvailable: 80%  # Allows 20% disruption
  
# Option 2: Count-based (good for smaller deployments)
spec:
  maxUnavailable: 1  # Allows 1 pod down at a time
```

## Pre-Upgrade PDB Checklist

```bash
# Check all PDBs for upgrade compatibility
kubectl get pdb -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,ALLOWED-DISRUPTIONS:.status.disruptionsAllowed

# Look for ALLOWED-DISRUPTIONS = 0 (these will block upgrades)
```

## Upgrade-Time Strategy

1. **Before upgrade:** Verify all PDBs have `disruptionsAllowed > 0`
2. **During upgrade:** Monitor for PDB blocks:
   ```bash
   kubectl get events -A --field-selector reason=DisruptionBudget
   ```
3. **Emergency fix:** Temporarily relax blocking PDBs, restore after upgrade

Your Services C and D are properly configured. Fix Services A and B before your next upgrade to prevent blocking issues.