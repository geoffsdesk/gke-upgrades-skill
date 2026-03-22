# PDB Audit for GKE Upgrades

I'll analyze each of your PDBs from a GKE upgrade safety perspective. The key risk is PDBs that are too restrictive, which can block node drains during upgrades.

## Your PDB Analysis

### 🚨 **High Risk - Will Block Upgrades**

**Service A: `minAvailable=100%`**
- **Risk:** CRITICAL - Will definitely block upgrades
- **Why:** 100% availability means zero disruption allowed. GKE cannot drain any nodes with Service A pods
- **Impact:** Upgrade will stall until you relax this PDB
- **Fix:** Change to `maxUnavailable=1` or `minAvailable=N-1` (where N is replica count)

**Service B: `maxUnavailable=0`**
- **Risk:** CRITICAL - Will definitely block upgrades  
- **Why:** Zero unavailable pods = 100% availability required, same as Service A
- **Impact:** Any node with Service B pods cannot be drained
- **Fix:** Change to `maxUnavailable=1`

### ✅ **Safe for Upgrades**

**Service C: `minAvailable=2` with 3 replicas**
- **Risk:** LOW - Safe for surge upgrades
- **Why:** Allows 1 pod disruption (3-2=1), enough for rolling drain
- **Upgrade behavior:** GKE can drain 1 node at a time containing Service C pods
- **Recommendation:** Keep as-is

**Service D: `maxUnavailable=1` with 5 replicas**
- **Risk:** LOW - Safe for upgrades
- **Why:** Explicitly allows 1 pod disruption
- **Upgrade behavior:** GKE can drain nodes normally
- **Recommendation:** Keep as-is

## Upgrade-Safe PDB Recommendations

```yaml
# BEFORE (risky)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 100%  # ❌ Blocks upgrades
  selector:
    matchLabels:
      app: service-a

# AFTER (upgrade-safe)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  maxUnavailable: 1   # ✅ Allows controlled disruption
  selector:
    matchLabels:
      app: service-a
```

```yaml
# BEFORE (risky)  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 0   # ❌ Blocks upgrades
  selector:
    matchLabels:
      app: service-b

# AFTER (upgrade-safe)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1   # ✅ Allows controlled disruption
  selector:
    matchLabels:
      app: service-b
```

## Pre-Upgrade PDB Checklist

Before your next upgrade, run these commands to identify problematic PDBs:

```bash
# Check all PDBs and their disruption allowance
kubectl get pdb -A -o wide

# Find PDBs that might block upgrades (0 disruptions allowed)
kubectl get pdb -A -o json | \
  jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name): \(.status.disruptionsAllowed) disruptions allowed"'

# Detailed view of risky PDBs
kubectl describe pdb -A | grep -E "Name:|Namespace:|Min available:|Max unavailable:|Allowed disruptions:"
```

## GKE Upgrade Behavior with PDBs

- **GKE timeout:** 1 hour maximum wait for pod eviction during surge upgrades
- **Respect period:** GKE respects PDBs during the drain process
- **Force eviction:** After 1 hour, GKE may force-evict pods even with restrictive PDBs
- **Notification:** GKE sends Cloud Logging events when PDBs block eviction

## Safe PDB Patterns by Workload Type

| Workload Type | Recommended PDB | Reasoning |
|---------------|-----------------|-----------|
| **Stateless web apps** | `maxUnavailable: 1` | Simple, allows rolling updates |
| **Databases (3 replicas)** | `minAvailable: 2` | Maintains quorum during upgrades |
| **Batch processors** | `maxUnavailable: 50%` | Can tolerate higher disruption |
| **Single replica services** | No PDB or `maxUnavailable: 1` | PDB provides no benefit with 1 replica |

## Temporary PDB Adjustment for Upgrades

If you need to keep restrictive PDBs for normal operations but relax them during upgrades:

```bash
# Before upgrade: temporarily relax Service A's PDB
kubectl patch pdb service-a-pdb -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"1"}}'

# After upgrade: restore original PDB
kubectl patch pdb service-a-pdb -n NAMESPACE \
  -p '{"spec":{"minAvailable":"100%","maxUnavailable":null}}'
```

## Action Items

1. **Immediate:** Fix Service A and Service B PDBs before your next upgrade
2. **Validate:** Run the PDB check commands above to confirm no other problematic PDBs
3. **Test:** Verify the new PDB settings work with your application's availability requirements
4. **Document:** Add PDB validation to your pre-upgrade checklist

**Bottom line:** Services A and B will definitely block your GKE upgrades. Services C and D are properly configured and safe.