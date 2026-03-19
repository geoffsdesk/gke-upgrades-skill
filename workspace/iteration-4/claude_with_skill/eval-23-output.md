# PDB Upgrade Safety Audit

I'll analyze each service's PDB configuration for upgrade safety. The key principle: **PDBs need to allow at least 1 pod disruption during upgrades**, or GKE will wait up to 1 hour trying to drain nodes before timing out.

## ❌ **RISKY - Will Block Upgrades**

### Service A: `minAvailable=100%`
**Risk Level: HIGH** - This will definitely block upgrades
- **Problem**: 100% availability means zero pods can ever be disrupted
- **Impact**: Nodes can't drain, upgrade will stall
- **Fix**: Change to `minAvailable=80%` or `maxUnavailable=1`

### Service B: `maxUnavailable=0` 
**Risk Level: HIGH** - Equivalent to minAvailable=100%
- **Problem**: Zero unavailable pods = no disruptions allowed
- **Impact**: Same as Service A - nodes can't drain
- **Fix**: Change to `maxUnavailable=1` (allows 1 pod disruption)

## ✅ **SAFE - Upgrade Compatible**

### Service C: `minAvailable=2` (3 replicas)
**Risk Level: LOW** - This is well-configured
- **Analysis**: Allows 1 pod disruption (3-2=1)
- **During upgrade**: Can have 1 pod down while nodes drain/upgrade
- **No changes needed**

### Service D: `maxUnavailable=1` (5 replicas)  
**Risk Level: LOW** - This is well-configured
- **Analysis**: Explicitly allows 1 pod disruption
- **During upgrade**: Can lose 1 pod during node operations
- **No changes needed**

## Recommended PDB Updates

```yaml
# Service A - Fix the blocking PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 80%  # or maxUnavailable: 20%
  selector:
    matchLabels:
      app: service-a

---
# Service B - Allow 1 disruption
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # Remove the 0
  selector:
    matchLabels:
      app: service-b
```

## Pre-Upgrade PDB Check Commands

Run these before your next upgrade to verify PDB safety:

```bash
# Check all PDBs allow at least 1 disruption
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAIL:.spec.minAvailable,MAX-UNAVAIL:.spec.maxUnavailable,ALLOWED:.status.disruptionsAllowed"

# Flag potentially problematic PDBs
kubectl get pdb -A -o json | jq -r '
  .items[] | 
  select(
    (.spec.minAvailable == "100%") or 
    (.spec.maxUnavailable == 0) or 
    (.status.disruptionsAllowed == 0)
  ) | 
  "\(.metadata.namespace)/\(.metadata.name) - RISKY"'
```

## General PDB Guidelines for GKE

| Service Type | Recommended PDB | Reasoning |
|--------------|----------------|-----------|
| **Stateless web apps** | `maxUnavailable: 25%` | Fast startup, can handle brief unavailability |
| **Databases/stateful** | `maxUnavailable: 1` | Conservative, but allows upgrades |
| **Single replica** | No PDB | PDB would block all operations |
| **Background workers** | `maxUnavailable: 50%` | Can tolerate higher disruption |

## Upgrade Strategy Impact

With your corrected PDBs, expect this upgrade behavior:

- **Services C & D**: Smooth upgrades, 1 pod down briefly per node drain
- **Services A & B** (after fixes): Will allow surge upgrades to proceed normally
- **Timeline**: Each node drain should complete in 2-5 minutes instead of timing out at 1 hour

The key insight: **PDBs are about voluntary disruptions** (upgrades, scaling down) not involuntary ones (node failures). Setting them too restrictively blocks maintenance operations that keep your cluster healthy and secure.